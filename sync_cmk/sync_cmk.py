#!/usr/bin/env python

import argparse
import logging
import json
import yaml
import flatdict
import urllib3
import ipaddress
from veritas.tools import tools
from veritas.sot import sot as sot
from veritas.checkmk import checkmk


default_config_file = "cmk.yaml"
snmp_credentials = None

def sync(args, sot, checkmk_config):
    """sync sot with cmk"""
    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    all_cmk_devices = cmk.get_all_hosts()
    all_sot_devices = sot.select('hostname', 'primary_ip4','location','custom_field_data') \
                         .using('nb.devices') \
                         .where(args.devices)

    # print(json.dumps(all_sot_devices, indent=4))
    # print(json.dumps(all_cmk_devices, indent=4))

    for device_properties in all_sot_devices:
        sot_device_name = device_properties.get('hostname')
        device_cmk_properties = next((item for item in all_cmk_devices if item['host_name'] == sot_device_name), {})
        
        # check if device is in cmk
        if len(device_cmk_properties) == 0:
            logging.info(f'device {sot_device_name} not found in cmk')

        sot_dev_config, cmk_dev_config = get_current_device_configs(sot, 
                                                            device_properties, 
                                                            device_cmk_properties,
                                                            checkmk_config)

        print(json.dumps(sot_dev_config, indent=4))
        print(json.dumps(cmk_dev_config, indent=4))

        attributes, htg, remove_attributes, folder = get_new_cmk_device_config(sot_dev_config, cmk_dev_config)
        logging.debug('---- new config ----')
        logging.debug(f'attributes: {attributes}')
        logging.debug(f'remove: {remove_attributes}')
        logging.debug(f'htg: {htg}')
        logging.debug(f'folder: {folder}')

        # now check what to do
        if folder:
            cmk.update_folders([{'folder': folder}], check_mk_config)

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

    sot_config['htg'] = get_cfield_from_sot(device_sot_properties, 'checkmk_htg', '=', 'tag_')
    # add mappings to our tags
    for mapping in check_mk_config.get('mappings',{}):
        sot_field = mapping.get('sot')
        sot_value = device_sot_properties.get('custom_field_data',{}).get(sot_field)
        cmk_field = mapping.get('cmk')
        if sot_value and sot_field and cmk_field:
            cmkf = 'tag_' + cmk_field
            logging.debug(f'mapping {sot_field} to {cmk_field}')
            sot_config['htg'].update({cmkf: sot_value})

    # check labels
    sot_config['labels'] = get_cfield_from_sot(device_sot_properties, 'checkmk_labels', ':', '')
    cmk_config['labels'] = device_cmk_properties.get('extensions',{}).get('attributes',{}).get('labels',{})

    # checking folder
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
    if len(sot_dev_config['snmp']) > 0 and len(cmk_dev_config['snmp']) == 0:
        # sot has SNMP config but not cmk
        snmp_equals = False
    elif len(sot_dev_config['snmp']) > 0 and len(cmk_dev_config['snmp']) > 0:
        # sot and cmk have snmp config => compare snmp keys
        for key, value in cmk_dev_config['snmp'].items():
            if key not in sot_dev_config['snmp'] or value != sot_dev_config[key]:
                snmp_equals = False
    elif len(sot_dev_config['snmp']) == 0 and len(cmk_dev_config['snmp']) > 0:
        # remove snmp config
        if not htg:
            htg = {}
        htg['tag_snmp_ds'] = 'no-snmp'
        htg['tag_agent'] = 'no-agent'

    if not snmp_equals:
        if not attributes:
            attributes = {}
        logging.debug(f'update snmp config')
        attributes.update({'snmp_community' : sot_dev_config['snmp']})
        attributes.update({'tag_agent': 'no-agent'})
        attributes.update({'tag_snmp_ds': 'snmp-v2'})

    # host tag groups
    # check if we have to add/update some host tag groups
    for key, value in sot_dev_config['htg'].items():
        if key in cmk_dev_config['htg'] and cmk_dev_config['htg'][key] == value:
            logging.debug(f'tag {key} of {hostname} matches')
        else:
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
        if not 'labels' in attributes:
            attributes['labels'] = {}
        attributes['labels'][key] = value
        labels_update = False
        if key in cmk_dev_config['labels'] and cmk_dev_config['labels'][key] != value:
            labels_update = True
        # remove the list of labels if no update is necessary
        if not labels_update and 'labels' in attributes:
            del attributes['labels']

    # folder
    if sot_dev_config['folder'] != cmk_dev_config['folder']:
        folder = sot_dev_config['folder']

    return attributes, htg, remove_attributes, folder

#
# internal methods
#

def get_snmp_credentials(sot, device_properties, check_mk_config):
    global snmp_credentials
    snmp = {}
    snmp_id = device_properties.get('custom_field_data',{}).get('snmp_credentials')

    name_of_repo = check_mk_config.get('credentials',{}).get('snmp',{}).get('repo')
    path_to_repo = check_mk_config.get('credentials',{}).get('snmp',{}).get('path')
    subdir = check_mk_config.get('credentials',{}).get('snmp',{}).get('subdir')
    filename = check_mk_config.get('credentials',{}).get('snmp',{}).get('filename')

    if snmp_credentials is None:
        # open repo
        repo = sot.repository(repo=name_of_repo, path=path_to_repo)
        # get SNMP credentials from SOT
        logging.debug(f'loading SNMP credentials from REPO {name_of_repo} FILE {subdir}/{filename}')
        snmp_credentials_text = repo.get(f'{subdir}/{filename}')
        snmp_credentials = yaml.safe_load(snmp_credentials_text).get('snmp',[])

    if snmp_id == 'unknown':
        logging.debug(f'this host has "unknown" SNMP-credentials')
        return None

    for cred in snmp_credentials:
        if cred.get('id') == snmp_id:
            snmp = dict(cred)
            # we use a security group to configure our devices but this 
            # group is not needed by checkmk
            if 'security_group' in snmp:
                del snmp['security_group']
            logging.debug(f'found SNMP credentials id:{snmp_id}')
            snmp_version = cred.get('version')
            if snmp_version == '1' or snmp_version == '2c':
                snmp['type'] = "v1_v2_community"
                del snmp['id']
                del snmp['version']
                
            elif snmp_version == 3:
                # rename value of auth_protocol
                # HMAC-SHA1-96 => SHA-1-96
                if 'privacy_protocol' in snmp and '256' in snmp['privacy_protocol']:
                    #logging.debug(f'checkmk does not support AES-256')
                    return None
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('HMAC-','')
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('SHA1','SHA-1')
                snmp['auth_protocol'] = snmp['auth_protocol'].replace('SHA2','SHA-2')
                del snmp['id']
                del snmp['version']

    if len(snmp) == 0:
        logging.debug(f'found no SNMP-Credentials for host')

    return snmp

def get_cfield_from_sot(properties, tagfield, seperator, key_prefix):
    response = {}
    htg_string = properties.get('custom_field_data',{}).get(tagfield,'')
    htgs = htg_string.replace(' ','').split(',')
    for htg in htgs:
        if len(htg) > 0:
            key, value = htg.split(seperator)
            response[f'{key_prefix}{key}'] = value
    return response

def get_folder_name(properties, folder_config):
    sot_cf_list = properties.get('custom_field_data',{})
    sot_tags = properties.get('tags')
    hostname = properties.get('hostname')
    folders = []
    fldrs = folder_config.get('template')
    if 'checkmk_folder' in sot_cf_list and len(sot_cf_list['checkmk_folder']) > 0:
        # if the custom field checkmk_folder is set in our SOT we use this field
        logging.debug(f'folder of {hostname}: {sot_cf_list["checkmk_folder"]}')
        return sot_cf_list["checkmk_folder"]
    elif '~' in fldrs:
        folders = fldrs.split('~')
    else:
        logging.debug(f'folder of {hostname}: {fldrs}')
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
                    logging.error(f'custom field {value} not found in custom_field_data, using default')
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
                        logging.error(f'{hostname} has no primary IP!!!')
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
                        ip = properties.get('primary_ip4',{}).get('address')
                        if ip is None:
                            logging.error(f'{hostname} has no primary IP!!!')
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

    logging.debug(f'folder of {hostname}: {folder}')
    return "~" + '~'.join(folder)


if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="check_mk config file")
    # what devices
    parser.add_argument('--devices', type=str, required=False, help="query to get list of devices")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="check_mk loglevel")
    # what to do
    parser.add_argument('--add-hosts', action='store_true', help='Add hosts to check_mk')
    parser.add_argument('--update-hosts', action='store_true', help='Update devices in check_mk')
    parser.add_argument('--add-host-tag-groups', action='store_true', help='Add host tag groups')
    parser.add_argument('--add-host-groups', action='store_true', help='Add host groups')
    parser.add_argument('--add-rules', action='store_true', help='Add rules to checkmk')
    parser.add_argument('--add-default-folders', action='store_true', help='Add default folders')
    parser.add_argument('--delete-hosts', action='store_true', help='Delete hosts in check_mk')
    parser.add_argument('--add-folders', action='store_true', help='Add folder if missing')
    # start a service discovery on the devices
    parser.add_argument('--service-discovery', action='store_true', help='Start Service discovery')
    parser.add_argument('--activate-changes', action='store_true', help='Start Service discovery')
    parser.add_argument('--repair-services', action='store_true', help='Start Service discovery')
    # status
    parser.add_argument('--show', type=str, required=False, help="Show status/rules/etc.")
    # sync
    parser.add_argument('--sync', action='store_true', help='Sync SOT and checkmk')
    parser.add_argument('--update-cmk', action='store_true', help='Update all hosts in checkmk')
    parser.add_argument('--missing-cmk', action='store_true', help='Add missing devices to checkmk')
    parser.add_argument('--remove-cmk', action='store_true', help='Remove devices from checkmk')
    parser.add_argument('--dry-run', action='store_true', help='Just print what to do')

    # parse arguments
    args = parser.parse_args()

    # read check_mk config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    with open(config_file) as f:
        check_mk_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(check_mk_config, ['check_mk', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(check_mk_config, ['check_mk', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(check_mk_config, ['check_mk', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=check_mk_config['sot']['token'],
                  ssl_verify=check_mk_config['sot'].get('ssl_verify', False),
                  url=check_mk_config['sot']['nautobot'])
    
    if args.sync or args.update_cmk or args.missing_cmk or args.remove_cmk:
        sync(args, sot, check_mk_config)