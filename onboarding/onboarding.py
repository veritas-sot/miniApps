#!/usr/bin/env python

import argparse
import sys
import pytricia
import yaml
import socket
import os
import json
import logging
import getpass
from slugify import slugify
from dotenv import load_dotenv, dotenv_values
from collections import defaultdict
from veritas.sot import sot as sot
from veritas.tools import tools
from veritas.devicemanagement import devicemanagement as dm
from onboarding import onboarding
from onboarding import required as required
from onboarding import cables as cables

# set default config file to your needs
default_config_file = "./conf/config.yaml"


def get_prefix_path(prefixe, ip):
    """
    the prefix path is used to get the default values of a device
    The path consists of the individual subpaths eg when the device 
    has the IP address 192.168.0.1 the path could be 
    192.168.0.1 / 192.168.0.0/16 / 0.0.0.0/0
    0.0.0.0 should always exist and set the default values.
    """
    prefix_path = []
    pyt = pytricia.PyTricia()

    # build pytricia tree
    for prefix_ip in prefixe:
        pyt.insert(prefix_ip, prefix_ip)

    prefix = pyt.get(ip)
    prefix_path.append(prefix)

    parent = pyt.parent(prefix)
    while (parent):
        prefix_path.append(parent)
        parent = pyt.parent(parent)
    return prefix_path[::-1]

def get_device_defaults(prefixe, ip):
    """
    the functions returns the default values of a device
    we use the prefix path and merge all values that are on the path
    0.0.0.0/0 should always exists and contain the default values like default-site
    or default-role 
    If you do not use default values the onboarding process can faile because of missing but
    required values like site name, model and so on 
    """
    if prefixe is None:
        return {}

    prefix_path = get_prefix_path(prefixe, ip)
    defaults = {}
    for prefix in prefix_path:
        # logging.debug(f'using prefix {prefix} for default_values')
        # because custom_fields is nested we have to save old values and
        # add the value if the custom_field is not present
        last_custom_fields = defaults.get('custom_fields',{})
        defaults.update(prefixe[prefix])
        for key, value in last_custom_fields.items():
            # do not overwrite values with None
            if value is not None and key not in defaults['custom_fields']:
                defaults['custom_fields'][key] = value
        # logging.debug(f'current defaults: {defaults}')
    return defaults

def write_hldm(hldm, directory="./hldm"):
    """
    write the high level data model to disk
    """
    hostname = hldm.get('name')
    if hostname:
        logging.info(f'writing HLDM of {hostname} to disk')
        filename = "%s/%s" % (directory, hostname)
        with open(filename, 'w') as f:
            f.write(json.dumps(hldm,indent=4))
            f.close()

def export_config_and_facts(device_config, device_facts, directory="./export"):
    config_filename = "%s/%s.conf" % (directory, device_facts.get('fqdn','__error__').lower())
    facts_filename = "%s/%s.facts" % (directory, device_facts.get('fqdn','__error__').lower())
    if '__error__' in config_filename or '__error__' in config_filename:
        logging.error('could not export config and facts')
        return

    # create directory if it does not exsists
    directory = os.path.dirname(config_filename)
    if not os.path.exists(directory):
        os.makedirs(directory)    

    logging.info(f'export config to {config_filename}')
    with open(config_filename, 'w') as f:
        f.write(device_config)
    logging.info(f'export facts to {facts_filename}')
    with open(facts_filename, 'w') as f:
        f.write(json.dumps(device_facts,indent=4))

def read_config_and_facts_from_file(hostname, onboarding_config):
    device_config = ""
    device_facts = {}

    directory = onboarding_config.get('directories', {}).get('export','export')

    config_filename = "./%s/%s.conf" % (directory, hostname.lower())
    facts_filename = "./%s/%s.facts" % (directory, hostname.lower())
    logging.debug(f'reading config from {config_filename} and facts from {facts_filename}')

    try:
        with open(config_filename, 'r') as f:
            device_config = f.read()
        with open(facts_filename, 'r') as f:
            device_facts = json.load(f)
    except Exception as exc:
        logging.error(f'could not import config or facts {exc}')
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
    logging.info(f'now gathering facts from {hostname}')
    device_facts = conn.get_facts()
    if device_facts is None:
        logging.error('got no facts; skipping device')
        if conn:
            conn.close()
        return None, None
    device_facts['args.device'] = device_ip

    # retrieve device config
    logging.info("getting running-config")
    try:
        device_config = conn.get_config("running-config")
    except Exception as exc:
        logging.error("could not receive device config from %s; got exception %s" % (device_ip, exc))
        return None, None
    if device_config is None:
        logging.error(f'could not retrieve device config from {device_ip}')
        conn.close()
        return None, None
    conn.close()

    return device_config, device_facts

if __name__ == "__main__":

    # init vars
    defaults = None
    device_facts = None
    device_names_in_sot = {}
    device_ip_in_sot = {}
    # devicelist is the list of devices we are processing
    devicelist = []

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--onboarding', action='store_true', help='add device to SOT')
    parser.add_argument('--interfaces', action='store_true', help='add interfaces to SOT')
    parser.add_argument('--vlans', action='store_true', help='add VLANs to SOT')
    parser.add_argument('--cables', action='store_true', help='add cables to SOT')
    parser.add_argument('--config-context', action='store_true', help='write config context to repo')
    parser.add_argument('--tags', action='store_true', help='write tags')
    parser.add_argument('--backup', action='store_true', help='write backup to repo')
    parser.add_argument('--show-facts', action='store_true', help='show facts only')
    parser.add_argument('--show-config', action='store_true', help='show config only')
    parser.add_argument('--update', action='store_true', help='update SOT even if device exists')
    parser.add_argument('--write-hldm', action='store_true', help='write HLDM to disk')
    parser.add_argument('--show-hldm', action='store_true', help='show HLDM only')
    parser.add_argument('--export', action='store_true', help='write config and facts to file')

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="onboarding config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="onboarding loglevel")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")

    # should we deactivate the polling of all devices from the sot to check if a device is present
    parser.add_argument('--no-polling', action='store_true', help="do not poll devices from SOT to check if device is present")

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
    parser.add_argument('--defaults', type=str, help="filename of defaulkt values in repo", required=False)
    parser.add_argument('--repo', type=str, required=False, help="name of default repo")
    parser.add_argument('--path', type=str, required=False, help="local path to default repo")
    parser.add_argument('--subdir', type=str, required=False, help="subdir of repo to get/write data from/to")

    # to overwrite the default device properties use these settings
    parser.add_argument('--hostname', type=str, required=False, help="this hostname is used when offline is used and device is ip")
    parser.add_argument('--site', type=str, required=False, help="set site of device")
    parser.add_argument('--device-role', type=str, required=False, help="set device role of device")
    parser.add_argument('--device-type', type=str, required=False, help="set device type of device")
    parser.add_argument('--manufacturer', type=str, required=False, help="set manufacturer of device")
    parser.add_argument('--platform', type=str, required=False, help="set platform of device")
    parser.add_argument('--status', type=str, required=False, help="set status of device")
    parser.add_argument('--add-tags', type=str, required=False, help="set tags of device")

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
    
    # set loglevel before init our SOT!!!
    tools.set_loglevel(args, onboarding_config)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=onboarding_config['sot']['token'], 
                  url=onboarding_config['sot']['nautobot'],
                  git=onboarding_config['git'])

    # get username and password either from profile or by get username / getpass or args
    username, password = tools.get_username_and_password(args, sot, onboarding_config)

    # get default values of prefixes. This is needed only once
    name_of_repo = args.repo or onboarding_config['git']['defaults']['repo']
    path_to_repo = args.path or onboarding_config['git']['defaults']['path']
    filename = args.defaults or onboarding_config['git']['defaults']['filename']
    logging.debug("reading %s from %s" % (filename, name_of_repo))
    default_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
    if default_repo.has_changes():
        logging.warning(f'repo {name_of_repo} has changes')
    defaults_str = default_repo.get(filename)
    if defaults_str is None:
        logging.error("could not load defaults")
        raise Exception('could not load defaults')

    # read the default values from our YAML file
    # the default values are wvery important. Using this values you
    # can easily import dozens of devices. To achieve this use default
    # values like 'unknown' or 'default-site'. After adding the devices
    # use the kobold script to modify tags, custom fields or mandatory
    # properties. 
    try:
        defaults_yaml = yaml.safe_load(defaults_str)
        if defaults_yaml is not None and 'defaults' in defaults_yaml:
            defaults = defaults_yaml['defaults']
    except Exception as exc:
        logging.critical("Cannot read default values; got exception: %s" % exc)
        raise Exception("cannot read default values")

    # get the list of all devices in our SOT
    # If you have a large number of devices in the database, this process will take a long time.
    # But controlling each device individually also takes a long time and requires a large 
    # number of database connections.
    if not args.no_polling:
        logging.debug('getting all devices from SOT')
        raw = sot.select('hostname', 'primary_ip4', 'platform', 'interfaces') \
                            .using('nb.devices') \
                            .normalize(False) \
                            .where()
        for device in raw:
            hostname = device.get('hostname')
            device_names_in_sot[hostname.lower()] = True
            primary_ip = device.get('primary_ip4',{}).get('address','').split('/')[0] if device.get('primary_ip4') else None
            if not primary_ip:
                logging.error(f'host {hostname} has not primary IPv4')
                continue
            for interface in device['interfaces']:
                if len(interface['ip_addresses']) > 0:
                    ip_address = interface['ip_addresses'][0].get('address').split('/')[0]
                    device_ip_in_sot[ip_address] = hostname.lower()

    # add inventory from SOT
    if args.sot:
        sot_devicelist = sot.select('id', 'hostname', 'primary_ip4', 'platform') \
                            .using('nb.devices') \
                            .normalize(False) \
                            .where(args.sot)

        for device in sot_devicelist:
            hostname = device.get('hostname')
            primary_ip = device.get('primary_ip4',{}).get('address','').split('/')[0]
            if len(primary_ip) == 0:
                devicelist.append({'id': device.get('id'), 'hostname': hostname, 'host': hostname})
            else:
                devicelist.append({'id': device.get('id'), 'hostname': hostname, 'host': primary_ip})

    # add inventory from file
    if args.inventory:
        if '.xlsx' in args.inventory:
            mapping = onboarding_config.get('onboarding',{}).get('mappings',{})
            table = tools.read_excel_file(f'{BASEDIR}/{args.inventory}')
            for row in table:
                d = {}
                for k,value in row.items():
                    key = mapping.get(k) if k in mapping else k
                    d[key] = value
                devicelist.append(d)
        elif '.csv' in args.inventory:
            with open(args.inventory) as f:
                config = yaml.safe_load(f.read())
                for d in config:
                    # the inventory includes host (IP), hostname (name) and platform (ios or nxos)
                    # check if hostname has no space in name
                    d['hostname'] = d['hostname'].split(' ')[0]
                    # use a simple filter to exclude devices
                    if args.filter:
                        if args.filter.lower() not in d['hostname'].lower():
                            continue
                    devicelist.append(d)
                f.close()
        else:
            logging.error(f'cannot read {args.inventory}; unknown file format')
            sys.exit()

    # add inventory from cli
    if args.device is not None:
        for d in args.device.split(','):
            devicelist.append({'host': d, 'hostname': d})

    devices_processed = 0
    devices_overall = len(devicelist)

    #
    # now loop through all devices and process one by one
    #
    # This is the main LOOP of this script
    #
    logging.info(f'processing {len(devicelist)} devices')
    for device_dict in devicelist:
        devices_processed += 1
        in_sot = False
        device_uuid = None
        # device might be an IP ADDRESS and not the name
        host_or_ip = device_dict.get('host').lower()
        # the hostname is ALWAYS lower case
        hostname = device_dict.get('hostname', host_or_ip).lower()
        export_directory = directory = "%s/%s" % (BASEDIR, onboarding_config.get('directories', {}).get('export','./export'))
        logging.info(f'processing {host_or_ip} {hostname} {devices_processed}/{devices_overall}')

        if args.export:
            export_file = "%s/%s.conf" % (export_directory, hostname)
            if os.path.exists(export_file) and not args.update:
                logging.debug(f'config for host {hostname} already exists in export directory')
                continue
        try:
            # maybe the user has set a hostname instead of an address
            device_ip = socket.gethostbyname(host_or_ip)
        except Exception as esc:
            if not args.use_import:
                logging.error("could not resolve ip address; we are unable to retrieve the config (%s)" % esc)
                continue
            else:
                logging.error("could not resolve ip address but config will be imported")
                # we are setting the ip to 0.0.0.0
                # in this case we get the default values. The config is imported
                # the imported config conatins the IP address
                device_ip = "0.0.0.0"

        if args.write_hldm:
            logging.info("writing HLDM to file instead of adding or updating the SOT")
        elif args.show_facts or args.export or args.show_config or args.show_hldm:
            # processed later
            pass
        else:
            # check if device is already in sot
            if args.no_polling:
                device_uuid = sot.get.id(item='device', name=hostname)
                in_sot = True if device_uuid else False
            else:
                in_sot = device_ip in device_ip_in_sot or hostname in device_names_in_sot

            if in_sot and not args.update:
                logging.info(f'device {hostname} is already in sot and update is not active')
                continue
            else:
                logging.debug(f'device {hostname} is new or will be updated')

        # get default values from SOT / the lowest priority is the prefix default
        device_defaults = get_device_defaults(defaults, device_ip)
        # the second priority is the inventory
        # save customfields; otherwise they are overwritten
        cfields = {}
        if 'custom_fields' in device_defaults:
            cfields = device_defaults['custom_fields']
        # remove custom_fields
        device_defaults['custom_fields'] = {}

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

        # the highest priority is the args
        args_dict = vars(args)
        for i in ['platform', 'site', 'device_type', 'device_role', 'manufacturer', 'status']:
            if i in args_dict and args_dict[i] is not None:
                device_defaults[i] = args_dict[i]

        # If 'ignore' is set, the device will not be processed.
        if device_defaults.get('ignore', False):
            logging.info(f'ignore set to true on {hostname}; skipping device')
            continue

        # If 'offline' is set we add the device using the default values to our SOT
        if device_defaults.get('offline', False):
            if args.onboarding:
                if args.hostname:
                    hostname = args.hostname
                logging.info(f'adding {hostname} offline to the sot')
                # we do not have any facts
                device_facts = {
                    "manufacturer": "cisco",
                    "model": onboarding_config['onboarding']['offline_config'].get('model','unknown'),
                    "serial_number": onboarding_config['onboarding']['offline_config'].get('serial_number','offline'),
                    "hostname": hostname,
                    "fqdn": hostname,
                    "args.device": device_ip
                }
                # read default offline device config
                offline_config = BASEDIR + "/" + onboarding_config['onboarding']['offline_config']['filename']
                logging.debug(f'reading offline config {offline_config}')
                # we do overwrite the device platform but only to parse the config right
                # the right value will be imported to nautobot
                device_platform = "ios"
                try:
                    with open(offline_config, 'r') as f:
                        device_config = f.read()
                        device_config = device_config.replace('__PRIMARY_IP__', device_ip)
                        device_config = device_config.replace('__HOSTNAME__', hostname)
                except Exception as exc:
                    logging.error(f'could not read offline config {exc}')
                    continue
            elif args.export:
                logging.info(f'device {hostname} is marked as "offline"')
                continue
        else:
            # this device is 'online'
            device_platform = device_defaults.get('platform','ios')
            device_config, device_facts = get_device_config_and_facts(args, 
                                                                      device_ip, 
                                                                      device_defaults, 
                                                                      username, 
                                                                      password, 
                                                                      hostname, 
                                                                      onboarding_config)

        if device_config is None or device_facts is None:
            logging.error(f'got no device config or no facts')
            continue

        # we keep in mind that this device is in our sot but 
        # only if we do not export config/facts
        # otherwise this would be exported as well!
        if not args.export:
            device_facts['is_in_sot'] = in_sot
            device_facts['id'] = device_dict.get('id', device_uuid)

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
        configparser = sot.configparser(config=device_config, platform=device_platform)
        if configparser.could_not_parse():
            continue

        logging.debug("calling onboarding")
        hldm = onboarding.onboarding(sot,
                                     args,
                                     device_facts,
                                     configparser,
                                     onboarding_config,
                                     device_defaults)

        if args.show_hldm:
            print('----- HLDM -----')
            print(json.dumps(hldm, indent=4))

        if args.write_hldm:
            directory = "%s/%s" % (BASEDIR, onboarding_config.get('directories', {}).get('hldm','./hldm'))
            write_hldm(hldm, directory)

    # after adding all devices to our sot we add the cables
    if args.cables and not args.write_hldm:
        for device_dict in devicelist:
            device = device_dict.get('host')
            platform = device_dict.get('platform')
            logging.debug("adding cables of %s to sot" % device)
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
                    logging.error('got no facts; skipping device')
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
