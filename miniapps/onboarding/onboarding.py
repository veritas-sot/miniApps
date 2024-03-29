#!/usr/bin/env python

import argparse
import socket
import os
import sys
import json
import urllib3
import yaml
import importlib
from loguru import logger
from dotenv import load_dotenv

# veritas
import veritas.logging
import veritas.profile
from veritas.onboarding import plugins
from veritas.sot import sot
from veritas.tools import tools
from veritas.onboarding import onboarding as onb


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

def get_business_logic(logic, platform):
    # we use our plugin architecture to use the right module
    plugin = plugins.Plugin()
    if logic == 'device':
        return plugin.get_business_logic_device(platform)
    elif logic == 'interface':
        return plugin.get_business_logic_interface(platform)
    elif logic == 'config_context':
        return plugin.get_business_logic_config_context(platform)
    else:
        return None

def onboard_device(sot, onboarding, args, device_facts, configparser, device_defaults, dry_run=False):
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
        device_fqdn = configparser.get_fqdn().lower()

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
        primary_address = socket.gethostbyname(device_facts['ip'])
        logger.info("no primary ip found using %s" % device_facts['ip'])

    # now onboard the device
    if args.onboarding:
        #
        # we use the plugin mechanism to call the business logic
        #
        # call the pre-processing business logic for the device
        logger.info('calling device pre-processing of business logic')
        #
        # this method modifies the device_defaults if needed (side effect!!!)
        #
        bl_device = get_business_logic('device', device_defaults.get('platform'))
        bl_device_obj = bl_device(configparser, device_facts)
        bl_device_obj.pre_processing(device_defaults)

        # now get the device properties
        # the device properties depend on the default values of the device
        logger.info('getting device properties')
        device_properties = onboarding.get_device_properties()
        if not device_properties:
            logger.error('failed getting device properties')
            return

        # call the post-processing business logic for the device
        logger.info('calling device post-processing of business logic')
        #
        # this method mofifies the device_properties if needed (side effect!)
        #
        bl_device_obj.post_processing(device_properties)

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
        bl_interface = get_business_logic('interface', device_defaults.get('platform'))
        bl_interface_obj = bl_interface(device_properties, configparser)
        interfaces = bl_interface_obj.post_processing(interfaces)

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
        sorted_dp = dict(sorted(device_properties.items()))
        for key, value in sorted_dp.items():
            logger.bind(extra='final dev').trace(f'key={key} value={value}')
        for trc_iface in interfaces:
            for key, value in trc_iface.items():
                logger.bind(extra='final inf').trace(f'key={key} value={value}')
        for trc_vlan in vlan_properties:
            for key, value in trc_vlan.items():
                logger.bind(extra='final vlan').trace(f'key={key} value={value}')

        # debugging output of all values
        logger.bind(extra='overview').debug(device_properties)

        if dry_run:
            print(f'summary of {device_fqdn}')
            if not device_facts['is_in_sot']:
                print(f'{device_fqdn} is a new host')
            else:
                print(f'{device_fqdn} found in SOT')
            print('device_properties:')
            print(json.dumps(device_properties, indent=4))
            print('interfaces')
            print(json.dumps(interfaces, indent=4))
            print(f'The primary interface is {primary_interface.get("name")}')
            return

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
                logger.debug('getting the list of all interfaces')
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
                        logger.info(f'adding new interface {interface_name}')                        
                        new_interfaces.append(interface)
                # update device 
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
                logger.info(f'updating primary IP of device {new_device.display} from {current_primary_ip} to {primary_address}')
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

def import_plugins(onboarding_config):
    # import plugins
    plugins = onboarding_config.get('plugins')
    for plugin in plugins:
        package = plugins.get(plugin).get('plugin_dir')
        subpackage = plugins.get(plugin).get('plugin')
        logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

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
    parser.add_argument('--dry-run', action='store_true', help='show key/values but do not onboard')
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="used other config file")
    # where do we get our data from
    parser.add_argument('--device', type=str, required=False, nargs="*", help="hostname or IP address of device(s) to onboard")
    parser.add_argument('--inventory', type=str, required=False, help="read inventory from file (xlsx, csv, yaml)")
    parser.add_argument('--sot', type=str, required=False, help="use nautobot to get devicelist")
    parser.add_argument('--import', action='store_true', dest='use_import', help='import config and facts from file')
    parser.add_argument('--filter', type=str, help='simple filter (hostname includes) to filter inventory')
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    group_profile = parser.add_mutually_exclusive_group(required=True)
    group_profile.add_argument('--profile', type=str, required=False, help="profile used to connect to devices")
    group_profile.add_argument('--username', type=str, required=False, help="username to connect to devices")
    parser.add_argument('--password', type=str, required=False, help="password to use to connect to devices")
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="log uuid used for journal")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    parser.add_argument('--debug-veritas', action='store_true', help="debug veritas lib")

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
        if not crypt_parameter:
            logger.error('no .env file and no salt.yaml file found')
            sys.exit()
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # read config
    onboarding_config = tools.get_miniapp_config('onboarding', BASEDIR, args.config)
    if not onboarding_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=onboarding_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='onboarding',
        uuid=args.uuid)

    # load profiles
    profile_config = tools.get_miniapp_config('onboarding', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=args.profile,
        username=args.username,
        password=args.password,
        ssh_key=None)

    # import onboarding plugins
    import_plugins(onboarding_config)

    # we need the SOT object to talk to it
    sot = sot.Sot(url=onboarding_config['sot']['nautobot'],
                  token=onboarding_config['sot']['token'],
                  ssl_verify=onboarding_config['sot'].get('ssl_verify', False),
                  debug=args.debug_veritas)

    # create onboarding instance
    onboarding = onb.Onboarding(
        sot=sot,
        onboarding_config=onboarding_config,
        profile=profile,
        tcp_port=args.port)

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
        sot_devicelist = sot.select('id, name, primary_ip4, platform') \
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
        for device in args.device:
            devicelist.append({'host': device, 'name': device})
        logger.info(f'added {len(args.device)} device(s) from cli')

    #
    # now loop through all devices and process one by one
    #
    # This is the main LOOP of this script
    #
    devices_processed = 0
    devices_overall = len(devicelist)
    logger.info(f'processing {len(devicelist)} device(s)')

    for device_properties_from_inventory in devicelist:
        devices_processed += 1

        # in_sot is later set to True if the device is already in the sot
        in_sot = False
        device_in_nb = None

        # device might be an IP ADDRESS and not the name
        # it is possible to use 'host' or 'ip' to import a device
        host_or_ip = device_properties_from_inventory.get('host', device_properties_from_inventory.get('ip'))
        if not host_or_ip:
            logger.error('failed to get host or IP; maybe you have empty rows in your inventory')
            continue

        # the hostname is ALWAYS lower case
        host_or_ip = host_or_ip.lower()
        hostname = device_properties_from_inventory.get('name', host_or_ip).lower()
        # there is no space in a hostname!!!
        hostname = hostname.split(' ')[0]
        logger.configure(extra={"extra": hostname})
        # write the hostname back
        device_properties_from_inventory['name'] = hostname
        export_directory = directory = "%s/%s" % (BASEDIR, onboarding_config.get('directories', {}).get('export','./export'))
        logger.info(f'processing host: {host_or_ip} hostname: {hostname} runs: {devices_processed}/{devices_overall}')

        # first we check if the file exists (and the user wants to export the config/facts)
        # this makes the export faster
        if args.export:
            export_file = "%s/%s.conf" % (export_directory, hostname)
            if os.path.exists(export_file) and not args.update:
                logger.debug(f'config for host {hostname} already exists in export directory')
                continue

        #
        # get the hostname of the device
        # we need the device name to import the config from a file
        #

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
            device_properties_from_inventory)

        # now we have all the device defaults
        # If 'ignore' is set, the device will not be processed.
        if device_defaults.get('ignore', False):
            logger.info(f'ignore set to true on {hostname}; skipping device')
            continue

        # If 'offline' is set we add the device using some default values
        if device_defaults.get('offline', False):
            if args.onboarding:
                logger.info(f'adding {hostname} offline to the sot')
                # we use our plugin architecture to use the right module
                plugin = plugins.Plugin()
                offline_importer = plugin.get_offline_importer()
                device_config, device_facts, platform = offline_importer(
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
                       device_defaults,
                       args.dry_run)

    # after adding all devices to our sot we add the cables
    # if args.cables:
    #     for device_properties_from_inventory in devicelist:
    #         device = device_properties_from_inventory.get('host')
    #         platform = device_properties_from_inventory.get('platform')
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

