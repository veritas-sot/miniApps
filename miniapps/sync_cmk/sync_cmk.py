#!/usr/bin/env python

import argparse
import yaml
import tabulate
import urllib3
import ipaddress
import os
import sys
from loguru import logger

import veritas.logging
import veritas.repo
from veritas.tools import tools
from veritas.sot import sot as veritas_sot
from veritas.checkmk import checkmk


snmp_credentials = None

def add_new_hosts(args, sot, checkmk_config):
    """add new hosts to cmk"""
    nn_of_devices_to_be_added = 0
    devices_to_be_added = []

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    all_cmk_devices = cmk.get_all_hosts()
    all_sot_devices = sot.select('hostname, primary_ip4, location, custom_field_data') \
                         .using('nb.devices') \
                         .where(args.devices)

    for device_properties in all_sot_devices:
        sot_device_name = device_properties.get('hostname')
        device_cmk_properties = next((item for item in all_cmk_devices if item['host_name'] == sot_device_name), {})
        
        # check if device is in cmk
        if len(device_cmk_properties) == 0:
            sot_dev_config,x = get_current_device_configs(sot, 
                                                          device_properties, 
                                                          device_cmk_properties,
                                                          checkmk_config)
            sot_dev_config.update({'hostname': sot_device_name})
            if not sot_dev_config.get('ip'):
                logger.info(f'device {sot_device_name} has no primary IP configured; ignoring host')
            else:
                logger.info(f'device {sot_device_name} not found in cmk')
                nn_of_devices_to_be_added += 1
                devices_to_be_added.append(sot_dev_config)
    
    if args.dry_run:
        print(f'{nn_of_devices_to_be_added}/{len(all_sot_devices)} devices are new')
        for d in devices_to_be_added:
            print(d)
    else:
        result = []
        logger.debug('updating folders...')
        cmk.update_folders(devices_to_be_added, 
                          checkmk_config.get('folders',{}).get('config',[]))
        # prepare device list
        device_list = prepare_device_list(devices_to_be_added)
        if args.no_bulk:
            for d in device_list:
                success = cmk.add_hosts([d])
                result.append({'host': d['hostname'], 'success': success})
            tab = tabulate.tabulate(result, headers="keys")
            print(tab)
        else:
            success = cmk.add_hosts(device_list)
            if success:
                print(f'added {len(device_list)} devices to cmk')
            else:
                print('could not add devices to cmk')

def remove_hosts(args, sot, checkmk_config):
    """remove hosts in cmk"""
    nn_of_devices_to_be_removed = 0
    devices_to_be_removed = []

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    all_cmk_devices = cmk.get_all_hosts()
    all_sot_devices = sot.select('hostname, primary_ip4, location, custom_field_data') \
                         .using('nb.devices') \
                         .where(args.devices)

    for device_properties in all_cmk_devices:
        # check if device is in cmk
        hostname = device_properties.get('host_name')
        if not any(d['hostname'] == hostname for d in all_sot_devices):
            logger.debug(f'{hostname} found in cmk but not in sot; removing it')
            nn_of_devices_to_be_removed += 1
            devices_to_be_removed.append(hostname)
    
    if args.dry_run:
        print(f'{nn_of_devices_to_be_removed}/{len(all_sot_devices)} devices found in cmk but not in sot')
        for d in devices_to_be_removed:
            print(d)

def update_hosts(args, sot, checkmk_config):
    """sync sot with cmk"""
    nn_of_devices_to_be_updated = 0
    nn_of_new_hosts = 0
    nn_of_success = 0
    nn_of_failed = 0
    devices_to_be_updated = []

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    all_cmk_devices = cmk.get_all_hosts()
    all_sot_devices = sot.select('hostname, primary_ip4, location, custom_field_data') \
                         .using('nb.devices') \
                         .where(args.devices)

    for device_properties in all_sot_devices:
        sot_device_name = device_properties.get('hostname')
        device_cmk_properties = next((item for item in all_cmk_devices if item['host_name'] == sot_device_name), {})
        
        # check if device is in cmk
        if len(device_cmk_properties) == 0:
            logger.info(f'device {sot_device_name} not found in cmk')
            nn_of_new_hosts += 1
            continue

        sot_dev_config, cmk_dev_config = get_current_device_configs(sot, 
                                                            device_properties, 
                                                            device_cmk_properties,
                                                            checkmk_config)

        attributes, htg, remove_attributes, folder = get_new_cmk_device_config(sot_dev_config, cmk_dev_config)
        if attributes or htg or remove_attributes or folder:
            nn_of_devices_to_be_updated += 1
            new_properties = {'host': device_properties['hostname'],
                              'attributes': attributes,
                              'remove_attributes': remove_attributes,
                              'htg': htg,
                              'folder': folder}

            if not args.dry_run:
                etag = cmk.get_etag(device_properties['hostname'])
                res_folder = res_update = True
                if folder:
                    res_folder = cmk.move_host_to_folder(device_properties['hostname'], etag, folder)
                if attributes or htg or remove_attributes:
                    res_update = cmk.update_host_in_cmk(device_properties['hostname'], etag, attributes, remove_attributes)
                success = res_folder and res_update
                new_properties.update({'success': success})
                if success:
                    nn_of_success += 1
                else:
                    nn_of_failed += 1

            devices_to_be_updated.append(new_properties)


    if nn_of_devices_to_be_updated > 0:
        devices_to_be_updated[0].keys()
        tab = tabulate.tabulate(devices_to_be_updated, headers="keys")
        print(tab)
    if nn_of_new_hosts > 0:
        print(f'there are {nn_of_new_hosts} hosts found in SOT; please add those hosts')
        # the result is written to the database
        result = {'app': 'sync_cmk',
                    'details': {
                      'entity': cmk,
                      'message':f'there are {nn_of_new_hosts} hosts found in SOT; please add those hosts'}
                    }
        logger.bind(result=result).journal(f'there are {nn_of_new_hosts} hosts found in SOT; please add those hosts')

    if args.dry_run:
        print(f'{nn_of_devices_to_be_updated}/{len(all_sot_devices)} devices to be updated')
    else:
        print(f'{nn_of_devices_to_be_updated}/{len(all_sot_devices)} were to be updated')
        print(f'success: {nn_of_success} failed: {nn_of_failed}')
        # the result is written to the database
        result = {'app': 'sync_cmk',
                    'details': {
                      'entity': cmk,
                      'message': f'success: {nn_of_success} failed: {nn_of_failed}'}
                    }
        logger.bind(result=result).journal(f'success: {nn_of_success} failed: {nn_of_failed}')

def get_current_device_configs(sot, device_sot_properties, device_cmk_properties, check_mk_config):
    """return difference between sot config and checkmk config of a host"""
    sot_config = {}
    cmk_config = {}

    # ip config
    s_ip = device_sot_properties['primary_ip4']
    sot_config['ip'] = s_ip.get('address','').split('/')[0] if s_ip else None
    cmk_config['ip'] = device_cmk_properties.get('extensions',{}).get('attributes',{}).get('ipaddress')

    # snmp config
    sot_config['snmp'] = get_snmp_credentials(sot, device_sot_properties, check_mk_config)
    cmk_config['snmp'] = device_cmk_properties.get('extensions',{}).get('attributes',{}).get('snmp_community',{})

    # check host group tags
    cmk_attributes = device_cmk_properties.get('extensions',{}).get('attributes',{})
    ignore = check_mk_config.get('defaults', {}).get('ignore_host_tag_groups')
    cmk_htg = {}
    # prepare the list with host tags of cmk
    for key, value in cmk_attributes.items():
        if key.startswith('tag_') and key not in ignore:
            cmk_htg[key] = value
    cmk_config['htg'] = cmk_htg

    # we are using two custom fields to set labels and host tag groups
    # 1. checkmk_htg
    #    format: tag_name=tag_value
    # 2. checkmk_labels
    #    format: labelname:labelvalue

    sot_config['htg'] = get_cfield_from_sot(device_sot_properties, 'checkmk_htg', '=', 'tag_')
    # add mappings to our tags
    for mapping in check_mk_config.get('mappings',{}):
        sot_field = mapping.get('sot')
        sot_value = device_sot_properties.get('custom_field_data',{}).get(sot_field)
        cmk_field = mapping.get('cmk')
        if sot_value and sot_field and cmk_field:
            cmkf = 'tag_' + cmk_field
            sot_config['htg'].update({cmkf: sot_value})

    # check labels
    sot_config['labels'] = get_cfield_from_sot(device_sot_properties, 'checkmk_labels', ':', '')
    cmk_config['labels'] = device_cmk_properties.get('extensions',{}).get('attributes',{}).get('labels',{})

    # check attributes
    cfg_attr = check_mk_config.get('custom_fields', {}).get('attributes', {})
    sot_cf_attributes = {}
    cmk_cf_attributes = {}
    for key,value in cfg_attr.items():
        # we are mapping key (custom field in sot) to value (attributes in cmk)
        sot_cf_attributes.update(get_cfield_from_sot(device_sot_properties, key, None, value))
        # cmk has the correct attribute already!
        cmk_cf_attributes[value] = device_cmk_properties.get('extensions',{}).get('attributes',{}).get(value,{})
    sot_config['cf_attributes'] = sot_cf_attributes
    cmk_config['cf_attributes'] = cmk_cf_attributes

    # checking folder
    # it is possible to set a static value in nautobot to configure the folder nane
    # the custom_field is named 'checkmk_folder'
    
    sot_config['folder'] = get_folder_name(device_sot_properties, check_mk_config.get('folders',{}).get('structure',{}))
    cmk_config['folder'] = device_cmk_properties.get('extensions',{}).get('folder')
    if cmk_config['folder']:
        cmk_config['folder'] = cmk_config['folder'].replace('/','~')

    return sot_config, cmk_config

def get_new_cmk_device_config(sot_dev_config, cmk_dev_config):
    """return new cmk config of this host"""

    attributes = None
    htg = None
    remove_attributes = None
    folder = None

    # check ip
    if sot_dev_config['ip'] != cmk_dev_config['ip']:
        if not attributes:
            attributes = {}
        attributes.update({'ipaddress' : sot_dev_config['ip']})

    # snmp
    snmp_equals = True
    if len(sot_dev_config.get('snmp',{})) > 0 and len(cmk_dev_config.get('snmp',{})) == 0:
        # sot has SNMP config but not cmk
        snmp_equals = False
    elif len(sot_dev_config.get('snmp',{})) > 0 and len(cmk_dev_config.get('snmp',{})) > 0:
        # sot and cmk have snmp config => compare snmp keys
        for key, value in cmk_dev_config['snmp'].items():
            #logger.debug(f'key: {key} value: {value}')
            if key not in sot_dev_config['snmp']:
                logger.debug(f'key {key} not found in cmk config')
                snmp_equals = False
            elif key in sot_dev_config['snmp'] and value != sot_dev_config['snmp'].get(key):
                logger.debug(f'key {key} differs in cmk config {value} vs. {sot_dev_config["snmp"].get(key)}')
                snmp_equals = False
    elif len(sot_dev_config.get('snmp',{})) == 0 and len(cmk_dev_config.get('snmp',{})) > 0:
        # remove snmp config
        if not htg:
            htg = {}
        htg['tag_snmp_ds'] = 'no-snmp'
        htg['tag_agent'] = 'no-agent'

    if not snmp_equals:
        if not attributes:
            attributes = {}
        logger.debug('update snmp config')
        attributes.update({'snmp_community' : sot_dev_config['snmp']})
        attributes.update({'tag_agent': 'no-agent'})
        attributes.update({'tag_snmp_ds': 'snmp-v2'})

    # host tag groups
    # check if we have to add/update some host tag groups
    for key, value in sot_dev_config['htg'].items():
        if key in cmk_dev_config['htg'] and cmk_dev_config['htg'][key] == value:
            logger.debug(f'tag {key} matches')
        else:
            if not attributes:
                attributes = {}
            attributes.update({key: value})
    # check if we have to remove some host tag groups
    for h in cmk_dev_config['htg']:
        # tag_snmp_ds and tag_agent must always be there
        if h in ['tag_snmp_ds', 'tag_agent','tag_address_family']:
            continue
        if h not in sot_dev_config['htg']:
            if not remove_attributes:
                remove_attributes = []
            remove_attributes.append(h)

    # check labels
    # if there is an update we have to update ALL labels not only the changes!
    for key, value in sot_dev_config['labels'].items():
        # prepare a list that contains ALL labels
        if 'labels' not in attributes:
            attributes['labels'] = {}
        attributes['labels'][key] = value
        labels_update = False
        if key in cmk_dev_config['labels'] and cmk_dev_config['labels'][key] != value:
            labels_update = True
        # remove the list of labels if no update is necessary
        if not labels_update and 'labels' in attributes:
            del attributes['labels']

    # custom fields to attributes mapping
    for key, value in sot_dev_config['cf_attributes'].items():
        if key in cmk_dev_config['cf_attributes'] and cmk_dev_config['cf_attributes'][key] == value:
            logger.debug(f'tag {key} matches')
        else:
            if not attributes:
                attributes = {}
            attributes.update({key: value})

    # folder
    if sot_dev_config['folder'] != cmk_dev_config['folder']:
        folder = sot_dev_config['folder']

    return attributes, htg, remove_attributes, folder

#
# internal methods
#

def prepare_device_list(devices):
    """prepare device list so that the list can be used to add devices to cmk"""
    entries = []
    for device in devices:
        # for each device build dict with mandatory attributes
        e = {'folder': device['folder'],
             'host_name': device['hostname'],
             'attributes': get_attributes(device)}
        entries.append(e)
    return entries

def get_attributes(device):
    attributes = {
        'ipaddress': device['ip'],
        'alias': device['hostname'],
    }

    if len(device['htg']) > 0:
        attributes.update(device['htg'])
    if len(device['labels']) > 0:
        attributes.update({'labels': device['labels']})
    
    if len(device['snmp']) > 0:
        snmp = device['snmp']
        if snmp.get('version') == 1:
            attributes.update({'management_snmp_community': snmp})
        else:
            attributes.update({'snmp_community': snmp})
            attributes.update({'tag_agent': 'no-agent'})
            attributes.update({'tag_snmp_ds': 'snmp-v2'})
    else:
        attributes.update({'tag_snmp_ds': 'no-snmp'})
        attributes.update({'tag_agent': 'no-agent'})

    return attributes

def get_snmp_credentials(sot, device_properties, check_mk_config):
    global snmp_credentials
    snmp = {}
    snmp_id = device_properties.get('custom_field_data',{}).get('snmp_credentials')

    name_of_repo = check_mk_config.get('credentials',{}).get('snmp',{}).get('repo')
    path_to_repo = check_mk_config.get('credentials',{}).get('snmp',{}).get('path')
    filename = check_mk_config.get('credentials',{}).get('snmp',{}).get('filename')

    if snmp_credentials is None:
        # open repo
        repo = veritas.repo.Repository(repo=name_of_repo, path=path_to_repo)
        # get SNMP credentials from SOT
        logger.debug(f'loading SNMP credentials from REPO {name_of_repo} FILE {filename}')
        snmp_credentials_text = repo.get(filename)
        snmp_credentials = yaml.safe_load(snmp_credentials_text).get('snmp',[])

    if snmp_id == 'unknown':
        logger.debug('this host has "unknown" SNMP-credentials')
        return {}

    for cred in snmp_credentials:
        if cred.get('id') == snmp_id:
            snmp = dict(cred)
            # we use a security group to configure our devices but this 
            # group is not needed by checkmk
            if 'security_group' in snmp:
                del snmp['security_group']
            logger.debug(f'found SNMP credentials id:{snmp_id}')
            snmp_version = cred.get('version')
            if snmp_version == '1' or snmp_version == '2c':
                snmp['type'] = "v1_v2_community"
                del snmp['id']
                del snmp['version']
                
            elif snmp_version == 3:
                # rename value of auth_protocol
                # HMAC-SHA1-96 => SHA-1-96
                if 'privacy_protocol' in snmp and '256' in snmp['privacy_protocol']:
                    #logger.debug(f'checkmk does not support AES-256')
                    return {}
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('HMAC-','')
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('SHA1','SHA-1')
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('SHA2','SHA-2')
                del snmp['id']
                del snmp['version']

    if len(snmp) == 0:
        logger.debug('found no SNMP-Credentials for host')

    return snmp

def get_cfield_from_sot(properties, tagfield, seperator, key_prefix):
    response = {}
    htg_string = properties.get('custom_field_data',{}).get(tagfield,'')
    if not htg_string:
        return response
    htgs = htg_string.replace(' ','').split(',')
    for htg in htgs:
        if len(htg) > 0:
            if seperator:
                key, value = htg.split(seperator)
                response[f'{key_prefix}{key}'] = value
            else:
                response[key_prefix] = htg
    return response

def get_folder_name(properties, folder_config):
    sot_cf_list = properties.get('custom_field_data',{})
    sot_tags = properties.get('tags')
    hostname = properties.get('hostname')
    folders = []
    fldrs = folder_config.get('template')
    if 'checkmk_folder' in sot_cf_list and len(sot_cf_list['checkmk_folder']) > 0:
        # if the custom field checkmk_folder is set in our SOT we use this field
        logger.debug(f'folder of {hostname}: {sot_cf_list["checkmk_folder"]}')
        return sot_cf_list["checkmk_folder"]
    elif '~' in fldrs:
        folders = fldrs.split('~')
    else:
        logger.debug(f'folder of {hostname}: {fldrs}')
        return fldrs

    folder = []
    for item in folders:
        # item is part of the path eg folder1 if path is folder1~folder2~folder3
        config = folder_config.get(item)
        default = config.get('default')
        fldr = None
        for key, value in config.items():
            if key == 'custom_field':
                fldr = sot_cf_list.get(value.replace('cf_',''))
                if fldr is None:
                    logger.error(f'custom field {value} not found in custom_field_data, using default')
                    fldr = default
            if key == 'property':
                vls = value.split('__')
                fldr = get_value(properties, vls)
            if key == 'cidr':
                fldr = None
                for item in value:
                    net = item.get('net')
                    p_ip = properties.get('primary_ip4',{})
                    ip = p_ip.get('address') if p_ip else None
                    if ip is None:
                        logger.error(f'{hostname} has no primary IP!!!')
                        fldr = default
                    else:
                        if ipaddress.ip_address(ip.split('/')[0]) in ipaddress.ip_network(net):
                            fldr = item.get('folder', default)
            if key == 'depending_on':
                for depends_on in value:
                    if 'cidr' in depends_on:
                        net = depends_on.get('net')
                        if not net:
                            continue
                        ip = None if not properties['primary_ip4'] else properties.get('primary_ip4',{}).get('address')
                        if ip is None:
                            logger.error(f'{hostname} has no primary IP!!!')
                            fldr = default
                        else:
                            if ipaddress.ip_address(ip.split('/')[0]) in ipaddress.ip_network(net):
                                fldr = depends_on.get('folder', default)
                                break
                    if 'property' in depends_on:
                        vls = depends_on.get('property').split('__')
                        value = get_value(properties, vls)
                        if depends_on.get('value') == value:
                            fldr = value
                            break
                    if 'custom_field' in depends_on:
                        cf = depends_on.get('custom_field')
                        if cf in sot_cf_list:
                            if sot_cf_list.get(cf) == depends_on.get('value'):
                                fldr = depends_on.get('folder')
                                break
                    if 'tag' in depends_on:
                        tag = depends_on.get('tag')
                        for items in sot_tags:
                            for k,v in items.items():
                                if tag == v:
                                    fldr = depends_on.get('folder')
                                    break

            if fldr is None:
                fldr = default
        # check if we have to replace the fldr; eg. cf__xxx to the value of the custom field xxx
        if 'cf__' in fldr:
            cf = fldr.split('cf__')[1]
            fldr = sot_cf_list.get(cf)
        elif 'prop__' in fldr:
            prop = fldr.split('__')
            # cut of the prop__ at the beginning!
            fldr = get_value(properties, prop[1:])

        if fldr is not None and fldr != 'None':
            if isinstance(fldr, int):
                fldr = str(fldr)
            folder.append(fldr)

    logger.debug(f'folder of {hostname}: {folder}')
    return "~" + '~'.join(folder)

def get_value(values, keys):
    if isinstance(values, list):
        my_list = []
        for value in values:
            my_list.append(get_value(value.get(keys[0]), keys[1:]))
        return my_list
    elif isinstance(values, str):
        return values
    if len(keys) == 1:
        return values.get(keys[0])
    return get_value(values.get(keys[0]), keys[1:])

def main(args_list=None):

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', default='sync_cmk.yaml', type=str, required=False, help="used config file")
    # what devices
    parser.add_argument('--devices', type=str, required=False, help="query to get list of devices")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # sync
    parser.add_argument('--update-hosts', action='store_true', help='Update hosts in checkmk')
    parser.add_argument('--add-hosts', action='store_true', help='Add missing devices to checkmk')
    parser.add_argument('--remove-hosts', action='store_true', help='Remove devices from checkmk')
    parser.add_argument('--dry-run', action='store_true', help='Just print what to do')
    parser.add_argument('--no-bulk', action='store_true', help='add host using a single bulk request')

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    check_mk_config = tools.get_miniapp_config('sync_cmk', BASEDIR, args.config)
    if not check_mk_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=check_mk_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='sync_cmk',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=check_mk_config['sot']['token'],
                          url=check_mk_config['sot']['nautobot'],
                          ssl_verify=check_mk_config['sot'].get('ssl_verify', False))

    if args.update_hosts:
        update_hosts(args, sot, check_mk_config)
    if args.add_hosts:
        add_new_hosts(args, sot, check_mk_config)
    if args.remove_hosts:
        remove_hosts(args, sot, check_mk_config)

if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../sync_cmk')
    import sync_cmk as sync_cmk

    sync_mk.main(logger, ['--profile', 'default', 
                          '--loglevel', 'debug',
                          '--devices', 'name=lab.local'])

    """
    main()
