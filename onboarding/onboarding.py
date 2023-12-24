#!/usr/bin/env python

import argparse
import sys
import yaml
import socket
import os
import json
import logging
import getpass
import urllib3
from loguru import logger
from ipaddress import IPv4Network
from dotenv import load_dotenv, dotenv_values
from collections import defaultdict
from veritas.sot import sot as sot
from veritas.tools import tools
from veritas.messagebus import messagebus
from veritas.devicemanagement import devicemanagement as dm
from onboarding import onboarding
from onboarding import cables as cables

# set default config file to your needs
default_config_file = "./conf/config.yaml"


def get_device_defaults(prefixe, ip):
    """
    the functions returns the default values of a device
    we use the prefix path and merge all values that are on the path
    0.0.0.0/0 should always exists and contain the default values like the location
    or the default-role 
    If you do not use default values the onboarding process can faile because of missing but
    required values 
    """
    if prefixe is None:
        return {}
    logger.debug(f'get device defaults of {ip}')
    """
    the prefix path is used to get the default values of a device
    The path consists of the individual subpaths eg when the device 
    has the IP address 192.168.0.1 the path could be 
    192.168.0.1 / 192.168.0.0/16 / 0.0.0.0/0
    0.0.0.0 should always exist and set the default values.
    """
    prefix_path = tools.get_prefix_path(prefixe, ip)
    defaults = {}
    for prefix in prefix_path:
        # logger.debug(f'using prefix {prefix} for default_values')
        # because custom_fields is nested we have to save old values and
        # add the value if the custom_field is not present
        last_custom_fields = defaults.get('custom_fields',{})
        defaults.update(prefixe[prefix])
        for key, value in last_custom_fields.items():
            # do not overwrite values with None
            if value is not None and key not in defaults['custom_fields']:
                defaults['custom_fields'][key] = value
        # logger.debug(f'current defaults: {defaults}')
    return defaults

def write_hldm(hldm, directory="./hldm"):
    """
    write the high level data model to disk
    """
    hostname = hldm.get('name')
    if hostname:
        logger.info(f'writing HLDM of {hostname} to disk')
        filename = "%s/%s" % (directory, hostname)
        with open(filename, 'w') as f:
            f.write(json.dumps(hldm,indent=4))
            f.close()

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

def read_config_and_facts_from_file(hostname, onboarding_config):
    device_config = ""
    device_facts = {}

    directory = onboarding_config.get('directories', {}).get('export','export')

    config_filename = "./%s/%s.conf" % (directory, hostname.lower())
    facts_filename = "./%s/%s.facts" % (directory, hostname.lower())
    logger.debug(f'reading config from {config_filename} and facts from {facts_filename}')

    try:
        with open(config_filename, 'r') as f:
            device_config = f.read()
        with open(facts_filename, 'r') as f:
            device_facts = json.load(f)
    except Exception as exc:
        logger.error(f'failed to import config or facts {exc}', exc_info=True)
        return None, None

    return device_config, device_facts

def get_device_config_and_facts(args, device_ip, device_defaults, username, password, hostname, onboarding_config):
    device_facts = {}
    conn = dm.Devicemanagement(ip=device_ip,
                               platform=device_defaults.get('platform','ios'),
                               manufacturer=device_defaults.get('manufacturer','cisco'),
                               username=username,
                               password=password,
                               port=args.port,
                               scrapli_loglevel=args.scrapli_loglevel)

    if args.use_import:
        return read_config_and_facts_from_file(hostname, onboarding_config)

    # retrieve facts like fqdn, model and serialnumber
    logger.info(f'now gathering facts from {hostname}')
    device_facts = conn.get_facts()

    if device_facts is None:
        logger.error('got no facts; skipping device')
        if conn:
            conn.close()
        return None, None
    device_facts['args.device'] = device_ip

    # retrieve device config
    logger.info("getting running-config")
    try:
        device_config = conn.get_config("running-config")
    except Exception as exc:
        logger.error(f'failed to receive device config from {device_ip}; got exception {exc}', exc_info=True)
        return None, None
    if device_config is None:
        logger.error(f'failed to retrieve device config from {device_ip}')
        conn.close()
        return None, None
    conn.close()

    return device_config, device_facts

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # init vars
    listener = None
    defaults = None
    device_facts = None
    device_names_in_sot = {}
    device_ip_in_sot = {}
    # devicelist is the list of devices we are processing
    devicelist = []

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--onboarding', action='store_true', help='add device to SOT')
    parser.add_argument('--primary-only', action='store_true', help='add PRIMARY interface only to SOT')
    parser.add_argument('--interfaces', action='store_true', help='add interfaces to SOT')
    parser.add_argument('--cables', action='store_true', help='add cables to SOT')
    parser.add_argument('--config-context', action='store_true', help='write config context to repo')
    parser.add_argument('--tags', action='store_true', help='write tags')
    parser.add_argument('--backup', action='store_true', help='write backup to repo')
    parser.add_argument('--show-facts', action='store_true', help='show facts only')
    parser.add_argument('--show-config', action='store_true', help='show config only')
    parser.add_argument('--update', action='store_true', help='update SOT even if device exists')
    parser.add_argument('--export', action='store_true', help='write config and facts to file')

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="used config file")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    #parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")

    # should we activate the polling of all devices from the sot to check if a device is present
    parser.add_argument('--polling', action='store_true', help="poll ALL devices from SOT to check if device is present")

    # where do we get our data from
    parser.add_argument('--device', type=str, required=False, help="hostname or IP address of device")
    parser.add_argument('--inventory', type=str, required=False, help="read inventory from file")
    parser.add_argument('--sot', type=str, required=False, help="use SOT to get devices")
    parser.add_argument('--import', action='store_true', dest='use_import', help='import config and facts from file')
    parser.add_argument('--filter', type=str, help='simple filter (hostname includes) to filter inventory')

    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False, help="username to connect to devices")
    parser.add_argument('--password', type=str, required=False, help="password to use to connect to devices")
    parser.add_argument('--profile', type=str, required=False, help="profile name to connect to devices")

    # to read the defaults values we use our sot (repo)
    parser.add_argument('--defaults', type=str, help="filename of default values in repo", required=False)
    parser.add_argument('--repo', type=str, required=False, help="name of default repo")
    parser.add_argument('--path', type=str, required=False, help="local path to default repo")
    parser.add_argument('--subdir', type=str, required=False, help="subdir of repo to get/write data from/to")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    # Connect the path with the '.env' file name
    load_dotenv(os.path.join(BASEDIR, '.env'))
    
    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    # read config from file
    with open(config_file) as f:
        onboarding_config = yaml.safe_load(f.read())

    # configure logger environment
    database, zeromq, loglevel, loghandler, logger_format = tools.get_logger_environment(
        onboarding_config,
        args.loglevel,
        args.loghandler)

    logger.configure(extra={"extra": "unset"})
    logger.remove()
    logger.add(loghandler, level=loglevel, format=logger_format)
    if database or zeromq:
        logger.debug(f'enabling veritas messagebus db: {database != None} zeroMQ: {zeromq != None}')
        logger.add(messagebus.Messagebus(database=database,
                                         zeromq=zeromq,
                                         app='onboarding'),
                level=loglevel)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=onboarding_config['sot']['token'],
                  ssl_verify=onboarding_config['sot'].get('ssl_verify', False),
                  url=onboarding_config['sot']['nautobot'],
                  git=onboarding_config['git'])

    # get username and password either from profile or by get username / getpass or args
    username, password = tools.get_username_and_password(args, sot, onboarding_config)

    # get default values of prefixes. This is needed only once
    name_of_repo = args.repo or onboarding_config['git']['defaults']['repo']
    path_to_repo = args.path or onboarding_config['git']['defaults']['path']
    filename = args.defaults or onboarding_config['git']['defaults']['filename']
    logger.debug("reading %s from %s" % (filename, name_of_repo))

    default_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
    if default_repo.has_changes():
        logger.warning(f'repo {name_of_repo} has changes')
    defaults_str = default_repo.get(filename)
    if defaults_str is None:
        logger.error("could not load defaults")
        raise Exception('could not load defaults')

    # read the default values from our YAML file
    # the default values are wvery important. Using this values you
    # can easily import dozens of devices. To achieve this use default
    # values like 'unknown' or 'default-location'. After adding the devices
    # use the kobold script to modify tags, custom fields or mandatory
    # properties. 
    try:
        defaults_yaml = yaml.safe_load(defaults_str)
        if defaults_yaml is not None and 'defaults' in defaults_yaml:
            defaults = defaults_yaml['defaults']
    except Exception as exc:
        logger.critical(f'failed to read default values; got exception: {exc}', exc_info=True)
        raise Exception("failed to read default values")

    # get the list of all devices in our SOT
    # If you have a large number of devices in the database, this process will take a long time.
    # But controlling each device individually also takes a long time and requires a large 
    # number of database connections.
    if args.polling:
        logger.debug('getting all devices from SOT')
        raw = sot.select('name', 'primary_ip4', 'platform', 'interfaces') \
                 .using('nb.devices') \
                 .where()
        for device in raw:
            hostname = device.get('name')
            device_names_in_sot[hostname.lower()] = True
            primary_ip = device.get('primary_ip4',{}).get('address','').split('/')[0] if device.get('primary_ip4') else None
            if not primary_ip:
                logger.error(f'host {hostname} has not primary IPv4')
                continue
            for interface in device['interfaces']:
                if len(interface['ip_addresses']) > 0:
                    ip_address = interface['ip_addresses'][0].get('address').split('/')[0]
                    device_ip_in_sot[ip_address] = hostname.lower()

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
        if '.xlsx' in args.inventory:
            # read mapping from miniapps config
            conf_dir = "%s/%s" % (onboarding_config.get('git').get('app_configs').get('path'),
                                  onboarding_config.get('git').get('app_configs').get('subdir'))
            directory = os.path.join(conf_dir, './onboarding/mappings/')

            filename = "%s/%s" % (directory, 
                onboarding_config.get('onboarding',{}).get('mappings',{}).get('inventory',{}).get('filename')
            )
            if filename:
                # read mapping from file
                logger.debug(f'reading mapping_config from {filename}')
                with open(filename) as f:
                    mapping_config = yaml.safe_load(f.read())
                column_mapping = mapping_config.get('mappings',{}).get('columns',{})
                value_mapping = mapping_config.get('mappings',{}).get('values',{})
            table = tools.read_excel_file(f'{BASEDIR}/{args.inventory}')
            for row in table:
                d = {}
                for k,v in row.items():
                    key = column_mapping.get(k) if k in column_mapping else k
                    if key in value_mapping:
                        if v == None:
                            value = value_mapping[key].get('None', v)
                        else:
                            value = value_mapping[key].get(v, v)
                    else:
                        value = v
                    # convert 'true' or 'false' to boolean values
                    if isinstance(value, str) and value.lower() == 'true':
                        value = True
                    if isinstance(value, str) and value.lower() == 'false':
                        value = False
                    d[key] = value
                devicelist.append(d)
        elif '.csv' in args.inventory:
            with open(args.inventory) as f:
                config = yaml.safe_load(f.read())
                for d in config:
                    # the inventory includes host (IP), hostname (name) and platform (ios or nxos)
                    # use a simple filter to exclude devices
                    if args.filter:
                        if args.filter.lower() not in d['name'].lower():
                            continue
                    devicelist.append(d)
                f.close()
        else:
            logger.error(f'cannot read {args.inventory}; unknown file or format')
            sys.exit()

    # add inventory from cli
    if args.device is not None:
        for d in args.device.split(','):
            devicelist.append({'host': d, 'name': d})

    devices_processed = 0
    devices_overall = len(devicelist)

    #
    # now loop through all devices and process one by one
    #
    # This is the main LOOP of this script
    #
    logger.info(f'processing {len(devicelist)} devices')
    for device_dict in devicelist:
        devices_processed += 1
        in_sot = False
        device_in_nb = None
        # device might be an IP ADDRESS and not the name
        # it is possible to use 'host' or 'ip' to import a device
        host_or_ip = device_dict.get('host', device_dict.get('ip')).lower()
        # the hostname is ALWAYS lower case
        hostname = device_dict.get('name', host_or_ip).lower()
        # there is no space in a hostname!!!
        hostname = hostname.split(' ')[0]
        logger = logger.bind(extra=hostname)
        # write the hostname back
        device_dict['name'] = hostname
        export_directory = directory = "%s/%s" % (BASEDIR, onboarding_config.get('directories', {}).get('export','./export'))
        logger.info(f'processing host_or_ip: {host_or_ip} hostname: {hostname} runs: {devices_processed}/{devices_overall}')

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
            if args.polling:
                in_sot = device_ip in device_ip_in_sot or hostname in device_names_in_sot
                logger.debug(f'polling set; device {hostname}; in_sot={in_sot}')
            else:
                # we have two cases; we have the name of the device (simple)
                # or just the IP address (use graphql to get device)
                if device_ip == hostname:
                    # we have an IP; get device object
                    device_in_nb = sot.get.device_by_ip(ip=device_ip)
                    logger.info(f'address {device_ip} belongs to {device_in_nb}')
                else:
                    device_in_nb = sot.get.device(name=hostname)
                in_sot = True if device_in_nb else False
                logger.debug(f'polling not set; device {hostname}; in_sot={in_sot}')

            if in_sot and not args.update:
                logger.info(f'device {hostname} is already in sot and update is not active')
                continue
            else:
                logger.debug(f'device {hostname} is new or will be updated')

        # get default values from SOT / the lowest priority is the prefix default
        device_defaults = get_device_defaults(defaults, host_or_ip)
        # the second priority is the inventory
        # save customfields; otherwise they are overwritten
        cfields = {}
        if 'custom_fields' in device_defaults:
            cfields = device_defaults['custom_fields']
        # remove custom_fields
        device_defaults['custom_fields'] = {}

        # now use the device_dict - that is the content of the csv/xlsx file
        for key, value in device_dict.items():
            # do not overwrite values with None
            if value is not None:
                device_defaults[key] = value

        # write default custom fields back to device_defaults
        for key, value in cfields.items():
            # overwrite None values if our value is not None otherwise delete None values
            if 'custom_fields' in device_defaults and \
                    key in device_defaults['custom_fields'] and \
                    device_defaults['custom_fields'][key] is None:
                if value is not None:
                    device_defaults['custom_fields'][key] = value
                else:
                    del device_defaults['custom_fields']
            if 'custom_fields' in device_defaults and \
                    key not in device_defaults['custom_fields'] and \
                    value is not None:
                device_defaults['custom_fields'][key] = value

        # now we have all the device defaults
        logger.debug(device_defaults)

        # If 'ignore' is set, the device will not be processed.
        if device_defaults.get('ignore', False):
            logger.info(f'ignore set to true on {hostname}; skipping device')
            continue

        # If 'offline' is set we add the device using some default values
        if device_defaults.get('offline', False):
            if args.onboarding:
                logger.info(f'adding {hostname} offline to the sot')
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
                device_defaults['primary_interface'] = {
                    'ip': primary_cidr,
                    'mask': primary_mask,
                    'name': primary_interface,
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

                if 'config' in device_defaults:
                    # should we use a local device config?
                    if device_defaults.get('config').lower() == 'none':
                        # no config at all / use minimal default config
                        logger.debug(f'no offline config found; use minimal config')
                        device_config = f'hostname {hostname}\n'
                        device_config += f'interface {primary_interface}\n'
                        device_config += f' ip address {device_ip} {primary_mask}\n'
                        offline_config = False
                    else:
                        # yes, the config was configured by the inventory
                        logger.debug(f'using offline config {device_defaults.get("config")}')
                        offline_config = BASEDIR + "/" + device_defaults.get('config')
                else:
                    # use default offline config
                    logger.debug(f'using default offline config')
                    offline_config = BASEDIR + "/" + onboarding_config['onboarding']['offline_config']['filename']

                if offline_config:
                    # read default offline device config
                    logger.debug(f'reading offline config {offline_config}')
                    try:
                        with open(offline_config, 'r') as f:
                            device_config = f.read()
                            device_config = device_config.replace('__PRIMARY_IP__', device_ip)
                            device_config = device_config.replace('__HOSTNAME__', hostname)
                            device_config = device_config.replace('__PRIMARY_INTERFACE__', primary_interface)
                            device_config = device_config.replace('__PRIMARY_MASK__', primary_mask)
                    except Exception as exc:
                        logger.error(f'failed to read offline config {exc}', exc_info=True)
                        continue
            elif args.export:
                logger.info(f'device {hostname} is marked as "offline"')
                continue
        else:
            # this device is 'online'
            # get config and facts from device
            platform = device_defaults.get('platform','ios')
            device_config, device_facts = get_device_config_and_facts(args, 
                                                                      device_ip, 
                                                                      device_defaults, 
                                                                      username, 
                                                                      password, 
                                                                      hostname, 
                                                                      onboarding_config)

        if device_config is None or device_facts is None:
            logger.error(f'got no device config or no facts')
            continue

        # we keep in mind that this device is in our sot but 
        # only if we do not export config/facts
        # otherwise this would be exported as well!
        if not args.export:
            device_facts['is_in_sot'] = in_sot
            device_facts['device_in_nb'] = device_in_nb

        if args.show_facts:
            print(json.dumps(dict(device_facts), indent=4))
            continue
        if args.show_config:
            print(device_config)
            continue
        if args.export:
            export_config_and_facts(device_config, device_facts, export_directory)
            continue

        # parse config / configparser is a dict that contains all necessary data
        configparser = sot.configparser(config=device_config, 
                                        platform=platform, 
                                        empty_config=len(device_config)==0)

        if configparser.could_not_parse():
            continue

        response = onboarding.onboarding(sot,
                                         args,
                                         device_facts,
                                         configparser,
                                         onboarding_config,
                                         device_defaults)

    # after adding all devices to our sot we add the cables
    if args.cables and not args.write_hldm:
        for device_dict in devicelist:
            device = device_dict.get('host')
            platform = device_dict.get('platform')
            logger.debug("adding cables of %s to sot" % device)
            conn = dm.Devicemanagement(ip=device,
                                       platform=platform,
                                       manufacturer="cisco",
                                       username=username,
                                       password=password,
                                       port=args.port,
                                       scrapli_loglevel=args.scrapli_loglevel)
            if device_facts is None:
                # result[device]['error'] = 'got no facts'
                device_facts = conn.get_facts()
                if device_facts is None:
                    logger.error('got no facts; skipping device')
                    conn.close()
                    continue
                device_facts['args.device'] = device
            cables.to_sot(sot,
                          conn,
                          device_facts,
                          device_defaults,
                          onboarding_config)
            conn.close()

    # if a backup for each device was written we have to add/commit/push the changes
    if args.backup:
        name_of_repo = args.repo or onboarding_config['git']['backups']['repo']
        path_to_repo = args.path or onboarding_config['git']['backups']['path']
        backup_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
        backup_repo.add_all()
        backup_repo.commit('backups written')
        backup_repo.push()

    if listener:
        listener.stop()