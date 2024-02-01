#!/usr/bin/env python

import argparse
import socket
import os
import sys
import json
import urllib3
import yaml
from loguru import logger
from ipaddress import IPv4Network
from dotenv import load_dotenv

import veritas.logging
from veritas.sot import sot
from veritas.tools import tools
from veritas.onboarding import onboarding as onb
from businesslogic import your_device as onboarding_bl_device
from businesslogic import your_interfaces as onboarding_bl_interfaces


def export_config_and_facts(device_config, device_facts, directory_name):
    config_filename = "%s/%s.conf" % (directory_name, device_facts.get('fqdn','__error__').lower())
    facts_filename = "%s/%s.facts" % (directory_name, device_facts.get('fqdn','__error__').lower())
    if '__error__' in config_filename or '__error__' in config_filename:
        logger.error('could not export config and facts')
        return

    # create directory if it does not exsists
    directory = os.path.dirname(config_filename)
    if not os.path.exists(directory):
        os.makedirs(directory)

    logger.info(f'export config to {config_filename}')
    with open(config_filename, 'w') as f:
        f.write(device_config)
    logger.info(f'export facts to {facts_filename}')
    with open(facts_filename, 'w') as f:
        f.write(json.dumps(device_facts,indent=4))

def offline_onboarding(device_ip, device_defaults, onboarding_config):
    """set device_facts and device_defaults, build device config and return config and platform"""

    # at the beginning we have no device_config
    device_config = None

    # we do not have any facts
    model = device_defaults.get('model', 
            onboarding_config['onboarding']['offline_config'].get('model','unknown'))
    serial = device_defaults.get('serial', 
                onboarding_config['onboarding']['offline_config'].get('serial','offline'))
    manufacturer = device_defaults.get('manufacturer', 
                    onboarding_config['onboarding']['offline_config'].get('manufacturer','cisco'))
    platform = device_defaults.get('platform', 
                    onboarding_config['onboarding']['offline_config'].get('platform','ios'))
    primary_interface = device_defaults.get('primary_interface', 
                    onboarding_config['onboarding']['offline_config'].get('primary_interface','primary_interface'))
    primary_description = device_defaults.get('primary_description', 
                    onboarding_config['onboarding']['offline_config'].get('primary_description','Primary Interface'))
    primary_mask = device_defaults.get('primary_mask', 
                    onboarding_config['onboarding']['offline_config'].get('primary_mask','255.255.255.255'))
    # we need cidr notation
    primary_ipv4 = IPv4Network(f'{device_ip}/{primary_mask}', strict=False)
    primary_cidr = f'{device_ip}/{primary_ipv4.prefixlen}'
    # the format of device_properties['primary_interface'] is:
    # {'ip': '192.168.0.2/32', 'mask': '255.255.255.255', 'name': 'primary_interface', 'description': 'primary interface'}

    # check if we have a dict or a string
    # we need the NAME of the primary interface and not a dict
    if isinstance(primary_interface, dict):        
        primary_interface_name = primary_interface.get('name','primary_interface')
    else:
        primary_interface_name = primary_interface

    offline_primary_interface = {
        'address': primary_cidr,
        'mask': primary_mask,
        'name': primary_interface_name,
        'description': primary_description
    }
    device_facts = {
        "manufacturer": manufacturer,
        "model": model,
        "serial_number": serial,
        "hostname": hostname,
        "fqdn": hostname,
        "args.device": device_ip
    }

    for key, value in offline_primary_interface.items():
        if key in device_defaults['primary_interface']:
            logger.bind(extra='off (=)').trace(f'key=primary_interface.{key} value={value}')
        else:
            logger.bind(extra='off (+)').trace(f'key=primary_interface.{key} value={value}')
        device_defaults['primary_interface'][key] = value

    if 'config' in device_defaults:
        # should we use a local device config?
        if device_defaults.get('config').lower() == 'none':
            # no config at all / use minimal default config
            logger.debug('no offline config found; use minimal config')
            device_config = f'hostname {hostname}\n'
            device_config += f'interface {primary_interface_name}\n'
            device_config += f' ip address {device_ip} {primary_mask}\n'
            offline_config = False
        else:
            # yes, the name of the config was configured by the inventory
            logger.debug(f'using offline config {device_defaults.get("config")}')
            offline_config = BASEDIR + "/" + device_defaults.get('config')
    else:
        # use default offline config
        logger.debug('using default offline config')
        offline_config = BASEDIR + "/" + onboarding_config['onboarding']['offline_config']['filename']

    if offline_config:
        # read offline device config
        logger.debug(f'reading offline config {offline_config}')
        try:
            with open(offline_config, 'r') as f:
                device_config = f.read()
                device_config = device_config.replace('__PRIMARY_IP__', device_ip)
                device_config = device_config.replace('__HOSTNAME__', hostname)
                device_config = device_config.replace('__PRIMARY_INTERFACE__', primary_interface_name)
                device_config = device_config.replace('__PRIMARY_MASK__', primary_mask)
        except Exception as exc:
            logger.error(f'failed to read offline config {exc}', exc_info=True)
            return {},{}, ""

    return device_config, device_facts, platform

def onboard_device(sot, onboarding, args, device_facts, configparser, device_defaults):
    """onboard new device to nautobot"""

    # we have some empty variables
    vlan_properties = []
    device_properties = None
    tag_properties = []
    new_device = None

    # we need the FQDN of the device
    if device_facts is not None and 'fqdn' in device_facts:
        device_fqdn = device_facts['fqdn'].lower()
    else:
        # get fqdn from config instead
        device_fqdn = configparser.get_fqdn()

    # set extra parameter to logger
    logger.configure(extra={"extra": device_fqdn})

    # set the name of the device
    if device_fqdn:
        device_defaults['name'] = device_fqdn
        logger.bind(extra='onb (=)').trace(f'key=name value={device_fqdn}')

    # get the "real" primary address of the device
    # the primary address is the ip address of the 'default' interface.
    # in most cases this is the Loopback or the Management interface
    # the order of the list we are looking for can be configured in the onboarding config
    primary_address = onboarding.get_primary_address()

    logger.debug('getting primary IP address')
    if primary_address is not None:
        logger.info(f'primary address is {primary_address}')
    else:
        # no primary interface found. Get IP of the device
        primary_address = socket.gethostbyname(device_facts['args.device'])
        logger.info("no primary ip found using %s" % device_facts['args.device'])

    # now onboard the device
    if args.onboarding:
        # call the pre-processing business logic
        logger.info('calling device pre-processing of business logic')
        # this method modifies the device_defaults if needed (side effect!)
        onboarding_bl_device.device_pre_processing(
            sot, 
            device_defaults, 
            configparser, 
            onboarding.get_onboarding_config())

        logger.info('getting device properties')
        # now get the device properties
        # the device properties depend on the default values of the device
        # but must no be identical
        device_properties = onboarding.get_device_properties()
        if not device_properties:
            logger.error('failed getting device properties')
            return

        # call the pre-processing business logic
        logger.info('calling device post-processing of business logic')
        # this method mofifies the device_defaults if needed (side effect!)
        onboarding_bl_device.device_post_processing(
                        sot, 
                        device_properties, 
                        configparser, 
                        onboarding.get_onboarding_config())
        # get vlan properties
        if args.interfaces or args.primary_only:
            logger.info('getting VLAN properties')
            vlan_properties = onboarding.get_vlan_properties(device_properties=device_properties)

        # get primary interface
        logger.debug('getting primary interface')
        primary_interface = onboarding.get_primary_interface(primary_address)

        if args.primary_only:
            logger.debug('adding primary interface to the list of interfaces')
            interfaces = [{'name': primary_interface.get('name'),
                           'ip_addresses': [{'address': primary_interface.get('address'),
                                             'status': primary_interface.get('status', {'name': 'Active'})
                                            }],
                           'description': primary_interface.get('description','Primary Interface'),
                           'type': primary_interface.get('type', '1000base-t'),
                           'status': primary_interface.get('status', {'name': 'Active'}) }]
        elif args.interfaces:
            logger.info('getting list of interfaces properties')
            interfaces = onboarding.get_interface_properties()
        else:
            logger.info('using empty list of interfaces')
            interfaces = []

        # call the post-processing business logic
        logger.info('calling interface post-processing of business logic')
        interfaces = onboarding_bl_interfaces.interfaces_post_processing(
                            sot,
                            interfaces,
                            device_properties,
                            configparser, 
                            onboarding.get_onboarding_config())

        # we have some internal attributes we have to remove
        if 'ip' in device_properties:
            del device_properties['ip']
        if 'ignore' in device_properties:
            del device_properties['ignore']
        if 'offline' in device_properties:
            del device_properties['offline']
        if 'config' in device_properties:
            del device_properties['config']

        # debug:print all values
        for key, value in device_properties.items():
            logger.bind(extra='final dev').trace(f'key={key} value={value}')
        for trc_iface in interfaces:
            for key, value in trc_iface.items():
                logger.bind(extra='final inf').trace(f'key={key} value={value}')
        for trc_vlan in vlan_properties:
            for key, value in trc_vlan.items():
                logger.bind(extra='final vlan').trace(f'key={key} value={value}')

        # debugging output of all values
        logger.bind(extra='overview').debug(device_properties)

        # we have all data we need to onboard the device
        # at this point the new device was NOT added to our SOT yet
        # we have either the primary interface or all interfaces and all vlans
        # now add device or update it
        # if the device is alredy in our SOT and arg.update is not set, the main
        # script has skipped this device
        if not device_facts['is_in_sot']:
            logger.debug('device not found in SOT; adding it')
            # add new device to SOT
            new_device = sot.onboarding \
                .interfaces(interfaces) \
                .vlans(vlan_properties) \
                .primary_interface(primary_interface.get('name')) \
                .add_prefix(False) \
                .add_device(device_properties)

            if not new_device:
                message = 'failed to add host to nautobot'
            else:
                message = 'added device to sot'
            result = {'app': 'onboarding',
                             'details': {
                                'entity': device_fqdn,
                                'message': message}
                     }
            logger.bind(result=result).journal(message)
        else:
            # update device properties; the device exists and args.update is set
            device_in_nb = device_facts.get('device_in_nb')
            if not device_in_nb:
                new_device = sot.get.device(name=device_fqdn)
            else:
                new_device = device_facts.get('device_in_nb')

            if not new_device:
                logger.error(f'could not get device {device_fqdn} from SOT')
                return
            else:
                logger.debug('updating device properties')
                new_device.update(device_properties)

            if args.interfaces or args.primary_only:
                # get ALL interfaces of our device
                all_interfaces = sot.get.interfaces(device_id=new_device.id)

            if args.interfaces:
                # if args.interfaces is set we add unknown interfaces to SOT
                # and update ALL known interfaces as well
                new_interfaces = []
                for interface in interfaces:
                    interface_name = interface.get('name','')
                    found = False
                    for nb_interface in all_interfaces:
                        if interface_name == nb_interface.display:
                            found = True
                            nb_interface.update(interface)
                            logger.info(f'updated interface {interface_name}')
                    if not found:
                        logger.debug(f'interface {interface_name} not found in SOT')
                        new_interfaces.append(interface)
                if len(new_interfaces) > 0:
                    sot.onboarding.add_prefix(False) \
                                  .assign_ip(True) \
                                  .add_interfaces(device=new_device, interfaces=new_interfaces)
                    logger.info(f'added {len(new_interfaces)} interface(s)')

                    result = {'app': 'onboarding',
                              'details': {
                                'entity': device_fqdn,
                                'message': f'added {len(new_interfaces)} interface(s)'}
                             }
                    logger.bind(result=result).journal(f'added {len(new_interfaces)} interface(s)')
            elif args.primary_only:
                # update primary interface
                for interface in interfaces:
                    interface_name = interface.get('name','')
                    primary_interface_found = False
                    for nb_interface in all_interfaces:
                        if interface_name == nb_interface.display:
                            primary_interface_found = True
                            sot.onboarding.add_prefix(False) \
                                          .assign_ip(True) \
                                          .update_interfaces(device=new_device, interfaces=interfaces)
                            result = {'app': 'onboarding',
                              'details': {
                                'entity': device_fqdn,
                                'message': f'updated primary interface {interface_name}'}
                             }
                            logger.bind(result=result).journal(f'updated primary interface {interface_name}')
                    if not primary_interface_found:
                        logger.info('no primary inteface found; seems to be a new one; adding it')
                        sot.onboarding.add_prefix(False) \
                                      .assign_ip(True) \
                                      .add_interfaces(device=new_device, interfaces=interfaces)

            # maybe the primary IP has changed. Check it and update if necessary
            if new_device.primary_ip4:
                current_primary_ip = new_device.primary_ip4.display.split('/')[0]
            else:
                # there is no primary IP
                current_primary_ip = "unknown or none"
                logger.info(f'the device {new_device.display} has no primary IP configured; setting it now')
            if current_primary_ip != primary_address:
                logger.info(f'updating primary IP of device {new_device.display} {current_primary_ip} vs. {primary_address}')
                sot.onboarding.set_primary_address(primary_address, new_device)

    if args.tags:
        # if the onboarding part did not run we need the device_properties
        if not device_properties:
            logger.info('getting device properties')
            device_properties = onboarding.get_device_properties()
        
        logger.info("getting tag properties")
        tag_properties = onboarding.get_tag_properties(device_fqdn,
                                                       device_properties,
                                                       device_facts)

        if not new_device:
            new_device = device_facts.get('device_in_nb', sot.get.device(name=device_fqdn))

        onboarding.add_tags(hostname=device_fqdn, 
                            tag_properties=tag_properties, 
                            device=new_device)

    # # now the most import part: the config_context
    # # do your own business logic in the "businesslogic" subdir
    # if args.config_context or args.write_hldm or args.show_hldm:
    #     logger.info("onboarding config context")
    #     cc = onboarding_config_context.to_sot(sot,
    #                                           args,
    #                                           device_fqdn,
    #                                           configparser,
    #                                           device_defaults,
    #                                           onboarding_config)

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # init vars
    defaults = None
    device_config = {}
    device_facts = {}
    device_names_in_sot = {}
    device_ip_in_sot = {}

    # devicelist is the list of devices we are processing
    devicelist = []

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--onboarding', action='store_true', help='onboard device to nautobot')
    parser.add_argument('--primary-only', action='store_true', help='add PRIMARY interface only to nautobot')
    parser.add_argument('--interfaces', action='store_true', help='add all interfaces to nautobot')
    parser.add_argument('--cables', action='store_true', help='add cables to nautobot')
    parser.add_argument('--config-context', action='store_true', help='write config context to repo')
    parser.add_argument('--tags', action='store_true', help='add device tags to nautobot')
    parser.add_argument('--update', action='store_true', help='update nautobot even if device exists')
    parser.add_argument('--export', action='store_true', help='write config and facts to file')
    parser.add_argument('--show-facts', action='store_true', help='show facts only and exit')
    parser.add_argument('--show-config', action='store_true', help='show config only and exit')

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="used other config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")

    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="log uuid used for journal")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")

    # where do we get our data from
    parser.add_argument('--device', type=str, required=False, help="hostname or IP address of device to onboard")
    parser.add_argument('--inventory', type=str, required=False, help="read inventory from file (xlsx, csv, yaml)")
    parser.add_argument('--sot', type=str, required=False, help="use nautobot to get devicelist")
    parser.add_argument('--import', action='store_true', dest='use_import', help='import config and facts from file')
    parser.add_argument('--filter', type=str, help='simple filter (hostname includes) to filter inventory')
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False, help="username to connect to devices")
    parser.add_argument('--password', type=str, required=False, help="password to use to connect to devices")
    parser.add_argument('--profile', type=str, required=False, help="profile used to connect to devices")
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    # to read the defaults values we use our sot (repo)
    parser.add_argument('--defaults', type=str, help="Use different default file", required=False)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('onboarding', BASEDIR, "salt.yaml")
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # create onboarding instance
    onboarding = onb.Onboarding(profile=args.profile, 
                                username=args.username, 
                                password=args.password)

    # get onboarding_config
    onboarding_config = onboarding.get_onboarding_config()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=onboarding_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='onboarding',
        uuid=args.uuid)

    # we need the SOT object to talk to it
    sot = sot.Sot(url=onboarding_config['sot']['nautobot'],
                  token=onboarding_config['sot']['token'],
                  ssl_verify=onboarding_config['sot'].get('ssl_verify', False),
                  debug=True)

    # get defaults
    if args.defaults:
        with open(args.default) as f:
            try:
                defaults = yaml.safe_load(f.read())
            except Exception as exc:
                logger.error(f'could not read or parse default values; got exception {exc}')
                sys.exit()
    else:
        defaults = onboarding.get_default_values_from_repo()

    # add inventory from SOT
    if args.sot:
        sot_devicelist = sot.select('id', 'name', 'primary_ip4', 'platform') \
                            .using('nb.devices') \
                            .where(args.sot)

        for device in sot_devicelist:
            hostname = device.get('name')
            primary_ip = device.get('primary_ip4',{}).get('address','').split('/')[0]
            if len(primary_ip) == 0:
                devicelist.append({'id': device.get('id'), 'name': hostname, 'host': hostname})
            else:
                devicelist.append({'id': device.get('id'), 'name': hostname, 'host': primary_ip})

    # add inventory from file
    if args.inventory:
        devicelist += onboarding.read_inventory(args.inventory)

    # add inventory from cli
    if args.device is not None:
        for d in args.device.split(','):
            devicelist.append({'host': d, 'name': d})

    #
    # now loop through all devices and process one by one
    #
    # This is the main LOOP of this script
    #
    devices_processed = 0
    devices_overall = len(devicelist)
    logger.info(f'processing {len(devicelist)} device(s)')

    for device_dict in devicelist:
        devices_processed += 1

        # in_sot is later set to True if the device is already in the sot
        in_sot = False
        device_in_nb = None

        # device might be an IP ADDRESS and not the name
        # it is possible to use 'host' or 'ip' to import a device
        host_or_ip = device_dict.get('host', device_dict.get('ip'))
        if not host_or_ip:
            logger.error('failed to get host or IP; maybe you have empty rows in your inventory')
            continue

        # the hostname is ALWAYS lower case
        host_or_ip = host_or_ip.lower()
        hostname = device_dict.get('name', host_or_ip).lower()
        # there is no space in a hostname!!!
        hostname = hostname.split(' ')[0]
        logger.configure(extra={"extra": hostname})
        # write the hostname back
        device_dict['name'] = hostname
        export_directory = directory = "%s/%s" % (BASEDIR, onboarding_config.get('directories', {}).get('export','./export'))
        logger.info(f'processing host: {host_or_ip} hostname: {hostname} runs: {devices_processed}/{devices_overall}')

        # we first check if the file exists (and the user wants to export the config/facts)
        # this makes the export faster
        if args.export:
            export_file = "%s/%s.conf" % (export_directory, hostname)
            if os.path.exists(export_file) and not args.update:
                logger.debug(f'config for host {hostname} already exists in export directory')
                continue
        try:
            # maybe the user has set a hostname instead of an address
            device_ip = socket.gethostbyname(host_or_ip)
        except Exception as exc:
            device_ip = host_or_ip
            if not args.use_import:
                logger.error(f'failed to resolve ip address; we are unable to retrieve the config ({exc})', exc_info=True)
                continue

        if args.show_facts or args.export or args.show_config:
            # processed later
            pass
        else:
            # check if device is already in sot
            device_in_nb = onboarding.device_in_sot(device_ip, hostname)
            in_sot = True if device_in_nb else False

            if in_sot and not args.update:
                logger.info(f'device {hostname} is already in sot and update is not active')
                continue
            else:
                logger.debug(f'device {hostname} is new or will be updated')

        # get device default of this host
        device_defaults = onboarding.get_device_defaults(
            host_or_ip, 
            device_dict)

        # now we have all the device defaults
        # logger.debug(f'device_defaults: {device_defaults}')
        # If 'ignore' is set, the device will not be processed.
        if device_defaults.get('ignore', False):
            logger.info(f'ignore set to true on {hostname}; skipping device')
            continue

        # If 'offline' is set we add the device using some default values
        if device_defaults.get('offline', False):
            if args.onboarding:
                logger.info(f'adding {hostname} offline to the sot')
                device_config, device_facts, platform = offline_onboarding(
                    device_ip, 
                    device_defaults, 
                    onboarding_config)
                if not device_config:
                    logger.error('got no device config')
                    continue
            elif args.export:
                logger.info(f'device {hostname} is marked as "offline"')
                continue
            else:
                logger.error('device is offline but --onboarding is not set')
                continue
        else:
            # this device is 'online'
            # get config and facts from device
            platform = device_defaults.get('platform','ios')
            device_config, device_facts = onboarding.get_device_config_and_facts(
                            device_ip=device_ip, 
                            device_defaults=device_defaults,
                            import_config=args.use_import,
                            import_filename=hostname)

        if device_config is None or device_facts is None:
            logger.error('got no device config or no facts')
            continue

        # we keep in mind that this device is in our sot but 
        # only if we do not export config/facts
        # otherwise this would be exported as well!
        if not args.export:
            device_facts['is_in_sot'] = in_sot
            device_facts['device_in_nb'] = device_in_nb
            device_facts['ip'] = device_ip

        if args.show_facts:
            print(json.dumps(dict(device_facts), indent=4))
            continue
        if args.show_config:
            print(device_config)
            continue
        if args.export:
            export_config_and_facts(device_config, device_facts, export_directory)
            continue

        # parse config to get interfaces and so on
        configparser = onboarding.parse_config(device_config, device_facts, device_defaults)
        # call onboarding
        onboard_device(sot,
                       onboarding,
                       args,
                       device_facts,
                       configparser,
                       device_defaults)

    # after adding all devices to our sot we add the cables
    # if args.cables:
    #     for device_dict in devicelist:
    #         device = device_dict.get('host')
    #         platform = device_dict.get('platform')
    #         logger.debug("adding cables of %s to sot" % device)
    #         conn = dm.Devicemanagement(ip=device,
    #                                    platform=platform,
    #                                    manufacturer="cisco",
    #                                    username=username,
    #                                    password=password,
    #                                    port=args.port,
    #                                    scrapli_loglevel=args.scrapli_loglevel)
    #         if device_facts is None:
    #             # result[device]['error'] = 'got no facts'
    #             device_facts = conn.get_facts()
    #             if device_facts is None:
    #                 logger.error('got no facts; skipping device')
    #                 conn.close()
    #                 continue
    #             device_facts['args.device'] = device
    #         onboarding_cables.to_sot(sot,
    #                                  conn,
    #                                  device_facts,
    #                                  device_defaults,
    #                                  onboarding_config)
    #         conn.close()

