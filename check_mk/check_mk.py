#!/usr/bin/env python

import argparse
import logging
import json
import yaml
import ipaddress
import re
import time
import pprint
import urllib3
from veritas.tools import tools
from veritas.sot import sot as sot


default_config_file = "check_mk.yaml"
snmp_credentials = None
_cache_all_cmk_devices = None
_cache_all_sot_devices = None

def start_session(check_mk_config):
    # baseurl http://hostname/site/check_mk/api/1.0
    url = check_mk_config.get('check_mk',{}).get('url')
    site = check_mk_config.get('check_mk',{}).get('site')
    username = check_mk_config.get('check_mk',{}).get('username')
    password = check_mk_config.get('check_mk',{}).get('password')
    api_url = "%s/%s/check_mk/api/1.0" % (url, site)

    logging.debug(f'starting session for {username} on {api_url}')
    check_mk = sot.rest(url=api_url, 
                        username=username,
                        password=password)
    check_mk.session()
    check_mk.set_headers({'Content-Type': 'application/json'})
    return check_mk

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

def add_config_to_checkmk(config, url, title, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    for item in config:
        title = item.get('value_raw', title)
        logging.info(f'adding {title}')
        response = check_mk.post(url=url, json=item)
        if response.status_code == 200:
            logging.info(f'{title} added')
        else:
            logging.error(f'adding {title} failed; error: {response.content}')

def add_default_folders(check_mk_config, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    for folder in check_mk_config.get('folders',{}).get('init',[]):
        name = folder.get('name')
        parent = folder.get('parent')
        data = {"name": name,
                "title": folder.get('title', name),
                "parent": parent
               }
        folder_config = get_folder_config(check_mk_config, name)
        if folder_config is not None:
            data.update({'attributes': folder_config})
        logging.debug(f'creating folder {name} in {parent}')
        response = check_mk.post(url=f"/domain-types/folder_config/collections/all", json=data)
        if response.status_code == 200:
            logging.info(f'folder {name} added in {parent}')
        else:
            logging.error(f'could not add folder; error: {response.content}')
            if response.status_code == 200:
                logging.info(f'folder {name} added in {parent}')
            else:
                logging.error(f'could not add folder; error: {response.content}')

def add_host_tag_groups(sot, host_tag_groups):
    simple_htg = []
    cfields = {}

    for htg in host_tag_groups:
        if any(d['ident'].startswith('sot__') for d in htg['tags']):
            for tag in htg.get('tags'):
                ident = tag.get('ident').replace('sot__','')
                if ident.startswith('prop__location'):
                    # query = "query{ location { name } }"
                    # raw_data = sot.get.query(query=query, parameter={})
                    raw_data = sot.select('location') \
                        .using('nb.devices') \
                        .normalize(False) \
                        .where()
                    if not 'set' in cfields:
                        cfields = {'location': set()}
                    for cf_data in raw_data:
                        for key, value in cf_data.items():
                            if key == 'name':
                                cfields['location'].add(value)
                if ident.startswith('cf_'):
                    raw_data = sot.select('hostname', 'custom_fields') \
                        .using('nb.devices') \
                        .normalize(False) \
                        .where()
                    for cf_data in raw_data:
                        for key, value in cf_data['custom_field_data'].items():
                            if key not in cfields:
                                cfields[key] = set()
                            cfields[key].add(value)
    for htg in host_tag_groups:
        if any(d['ident'].startswith('sot_') for d in htg['tags']):
            tags_copy = []
            for tag in htg.get('tags'):
                if not tag['ident'].startswith('sot__'):
                    tags_copy.append(tag)
            for tag in htg.get('tags'):
                # each tag contains ident and title
                ident = tag.get('ident')
                title = tag.get('title')
                ident = ident.replace('sot__','')
                for tag_property in ['cf_', 'prop__']:
                    if ident.startswith(tag_property):
                        name = ident.split(tag_property)[1]
                        if name in cfields:
                            for i in cfields[name]:
                                if not any(d['ident'] == i for d in tags_copy):
                                    tags_copy.append({'ident': i, 'title': i})
            htg['tags'] = tags_copy
    add_config_to_checkmk(host_tag_groups, '/domain-types/host_tag_group/collections/all', 'host tag groups')   

def get_all_hosts(check_mk=None):
    devicelist = []
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    # get a list of all hosts of check_mk
    response = check_mk.get(url=f"/domain-types/host_config/collections/all",
                                      params={"effective_attributes": False, },
                                      format='object')
    if response.status_code != 200:
        logging.error(f'got status code {all_check_mk_hosts.status_code}; giving up')
        return []
    devices = response.json().get('value')
    for device in devices:
        devicelist.append({'host_name': device.get('title'),
                           'folder': device.get('extensions',{}).get('folder'),
                           'ipaddress': device.get('extensions',{}).get('attributes',{}).get('ipaddress'),
                           'snmp': device.get('extensions',{}).get('attributes',{}).get('snmp_community'),
                           #'attributes': device.get('extensions',{}).get('attributes',{}),
                           'extensions': device.get('extensions',{})
                          })
    return devicelist

def get_all_host_tags(check_mk):
    host_tags = {}
    response = check_mk.get(url=f"/domain-types/host_tag_group/collections/all")
    for tag in response.json().get('value'):
        del tag['links']
        host_tag = tag.get('id',{})
        host_tags[host_tag] = tag.get('extensions',{}).get('tags')
    
    return host_tags

def get_folder_config(check_mk_config, folder_name):
    folders_config = check_mk_config.get('folders',{}).get('config')
    if folders_config is None:
        return None

    default = None
    for folder in folders_config:
        if folder['name'] == folder_name:
            response = dict(folder)
            del response['name']
            return response
        elif folder['name'] == 'default':
            response = dict(folder)
            del response['name']
            default = response
    return default

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
                    ip = properties.get('primary_ip4',{}).get('address')
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

def get_snmp_credentials(sot, properties, check_mk_config, snmp_id=None):
    global snmp_credentials
    snmp = {}
    sot_cf_list = properties.get('custom_field_data',{})
    if snmp_id:
        snmp_id = args.snmp_id
        logging.debug(f'overwriting SNMP; using {snmp_id}')
    else:
        snmp_id = sot_cf_list.get('snmp_credentials')

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

def get_host(host, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    params={"effective_attributes": False}
    response = check_mk.get(url=f"/objects/host_config/{host}", params=params)
    if response.status_code == 404:
        return None, None
    return response.headers.get('ETag'), response.json()

def get_cfield_from_sot(properties, tagfield, seperator, key_prefix):
    response = {}
    htg_string = properties.get('custom_field_data',{}).get(tagfield,'')
    htgs = htg_string.replace(' ','').split(',')
    for htg in htgs:
        if len(htg) > 0:
            key, value = htg.split(seperator)
            response[f'{key_prefix}{key}'] = value
    return response

def update_folders(devices, check_mk_config, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    for device in devices:
        fldrs = device.get('folder')
        response = check_mk.get(url=f"/objects/folder_config/{fldrs}")
        status = response.status_code
        if status == 200:
            logging.debug(f'{fldrs} found in check_mk')
        elif status == 404:
            # one or more parent folders are missing
            # we have to check the complete path
            logging.debug(f'{fldrs} does not exist; creating it')
            path = fldrs.split('~')
            for i in range(1, len(path)):
                pth = '~'.join(path[1:i])
                logging.debug(f'checking if ~{pth} exists')
                response = check_mk.get(url=f"/objects/folder_config/~{pth}")
                if response.status_code == 404:
                    logging.debug(f'{pth} does not exists')
                    i = pth.rfind('~')
                    name = pth[i+1:]
                    if i == -1:
                        parent = "~"
                    else:
                        parent = "~%s" % pth[0:i]
                    data = {"name": name, 
                            "title": name, 
                            "parent": parent }
                    folder_config = get_folder_config(check_mk_config, name)
                    if folder_config is not None:
                        data.update({'attributes': folder_config})
                    logging.debug(f'creating folder {name} in {parent}')
                    response = check_mk.post(url=f"/domain-types/folder_config/collections/all", json=data)
                    if response.status_code == 200:
                        logging.info(f'folder {name} added in {parent}')
                    else:
                        logging.error(f'could not add folder; error: {response.content}')
            # now we have the path upto our folder
            i = fldrs.rfind('~')
            name = fldrs[i+1:]
            if i == -1:
                parent = "~"
            else:
                parent = fldrs[0:i]
            logging.debug(f'creating folder {name} in {parent}')
            data = {"name": name, 
                    "title": name, 
                    "parent": parent }
            folder_config = get_folder_config(check_mk_config, name)
            if folder_config is not None:
                        data.update({'attributes': folder_config})
            response = check_mk.post(url=f"/domain-types/folder_config/collections/all", json=data)
            if response.status_code == 200:
                logging.info(f'folder {name} added in {parent}')
            else:
                logging.error(f'could not add folder; error: {response.content}')
        else:
            logging.debug(f'got status: {status}')

def add_to_check_mk(devices, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    data = {"entries": devices }
    params={"bake_agent": False}
    host = check_mk.post(url=f"/domain-types/host_config/actions/bulk-create/invoke",
                         json=data, 
                         params=params)
    status = host.status_code
    if status == 200:
        logging.info(f'host added to check_mk')
    elif status == 500:
        logging.error(f'got status {status}; maybe host is already in check_mk')
    else:
        logging.error(f'got status {status}; error: {host.content}')

def start_discovery(check_mk_config, devices, check_mk=None, bulk=True):

    if bulk:
        start_bulk_discovery(check_mk_config, devices, check_mk)
    else:
        start_single_discovery(check_mk_config, devices, check_mk)

def start_single_discovery(check_mk_config, devices, check_mk=None):
    logging.info('starting Host discovery')
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    for device in devices:
        hostname = device.get('host_name')
        logging.info(f'starting discovery on {hostname}')
        # in cmk 2.2 you can add: 'do_full_scan': True,
        data = {'host_name': hostname, 
                'mode': 'fix_all'}
        response = check_mk.post(url=f"/domain-types/service_discovery_run/actions/start/invoke", json=data)
        status = response.status_code
        if status == 200:
            logging.info('started successfully')
        else:
            logging.error(f'status {status}; error: {response.content}')

def start_bulk_discovery(check_mk_config, devices, check_mk=None):
    logging.info('starting Host discovery')
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    
    hostnames = []
    for device in devices:
        hostnames.append(device.get('host_name'))
        logging.debug(f'added {device.get("host_name")} to the list of hosts to discover')
    data = {'hostnames': hostnames,
            'mode': 'fix_all',  # fix_all, refresh, tabula_rasa
            'do_full_scan': True,
            'bulk_size': 10,
            'ignore_errors': True}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    response = check_mk.post(url=f"/domain-types/discovery_run/actions/bulk-discovery-start/invoke", 
                             json=data,
                             headers=headers)
    status = response.status_code
    if status == 200:
        logging.info('discovery started successfully')
    else:
        logging.error(f'status {status}; error: {response.content}')

def activate_all_changes(check_mk_config, check_mk=None):
    logging.info('activating all changes')
    site = site = check_mk_config.get('check_mk',{}).get('site')
    if check_mk is None:
        check_mk = start_session(check_mk_config)
    
    response = _activate_etag(check_mk, '*',[ site ])
    if response.status_code not in {200, 412}:
        logging.error(f'got status {response.status_code} could not activate changes; error: {response.content}')
        return

def _activate_etag(check_mk, etag, site):
    headers={
            "If-Match": etag,
            "Content-Type": 'application/json',
        }
    data = {"redirect": False,
            "sites": site,
            "force_foreign_changes": True}

    return check_mk.post(url=f"/domain-types/activation_run/actions/activate-changes/invoke", json=data, headers=headers)

def prepare_host_data(sot, properties, check_mk_config, snmp_id=None, check_mk=None):
    
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    # static values
    hostname = properties.get('hostname')
    if properties.get('primary_ip4') is None:
        logging.error(f'host {hostname} has no primary IP ... skipping')
        return None
    ip_address = properties.get('primary_ip4',{}).get('address').split('/')[0]
    site = properties.get('location',{}).get('name')
    custom_fields = properties.get('custom_field_data')

    # folder, tags, and snmp credentials are dynamic
    folder = get_folder_name(properties, check_mk_config.get('folders',{}).get('structure',{}))
    snmp = get_snmp_credentials(sot, properties, check_mk_config, snmp_id)
    host_tags = get_cfield_from_sot(properties, 'checkmk_htg', '=', 'tag_')
    labels = get_cfield_from_sot(properties, 'checkmk_labels', ':', '')

    # add mappings to our should_be tags
    for mapping in check_mk_config.get('mappings',{}):
        custom_fields = properties.get('custom_field_data')
        sot_field = mapping.get('sot')
        sot_value = custom_fields.get(sot_field)
        cmk_field = mapping.get('cmk')
        if sot_field and cmk_field:
            cmkf = 'tag_' + cmk_field
            logging.debug(f'mapping {sot_field} to {cmk_field}')
            host_tags.update({cmkf: sot_value})
  
    attributes = {
            'ipaddress': ip_address,
            'alias': hostname,
        }

    if len(host_tags) > 0:
        attributes.update(host_tags)
    if len(labels) > 0:
        attributes.update({'labels': labels})
    
    if snmp and len(snmp) > 0:
        if snmp.get('version') == 1:
            logging.debug(f'activating SNMPv1; please be careful')
            attributes.update({'management_snmp_community': snmp})
        else:
            logging.debug(f'activating SNMPv2/v3')
            attributes.update({'snmp_community': snmp})
            attributes.update({'tag_agent': 'no-agent'})
            attributes.update({'tag_snmp_ds': 'snmp-v2'})
    else:
        attributes.update({'tag_snmp_ds': 'no-snmp'})
        attributes.update({'tag_agent': 'no-agent'})

    return {
        'folder': folder,
        'host_name': hostname,
        'attributes': attributes
    }

def build_list(sot, devices, snmp_id, check_mk_config):
    all_check_mk_hosts = {}
    check_mk = start_session(check_mk_config)
    list_of_devices = []

    # get a list of all hosts of check_mk
    response = check_mk.get(url=f"/domain-types/host_config/collections/all",
                            params={"effective_attributes": False, },
                            format='object')
    if response.status_code != 200:
        logging.error(f'got status code {all_check_mk_hosts.status_code}; giving up')
        return

    for device in get_all_hosts(check_mk):
        hostname = device.get('host_name')
        all_check_mk_hosts[hostname] = device

    for device in devices:
        hostname = device.get('hostname')
        if hostname in all_check_mk_hosts:
            logging.info(f'host {hostname} is already in check_mk')
        else:
            logging.info(f'host {hostname} NOT found in check_mk')
            device_data = prepare_host_data(sot, device, check_mk_config, snmp_id, check_mk)
            if not device_data is None:
                list_of_devices.append(device_data)

    return list_of_devices

def move_host_to_folder(hostname, etag, new_folder, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    data={"target_folder": new_folder}
    headers={
        "If-Match": etag,
        "Content-Type": 'application/json',
    }
    logging.debug(f'sending request {data} {headers}')
    response = check_mk.post(url=f"/objects/host_config/{hostname}/actions/move/invoke", 
                             json=data,
                             headers=headers)
    status = response.status_code
    if status == 200:
        logging.info('moved successfully')
    else:
        logging.error(f'status {status}; error: {response.content}')

def update_host_in_cmk(hostname, etag, update_attributes, remove_attributes, check_mk):
    logging.info(f'updating host {hostname}')
    data = {}
    if len(update_attributes) > 0:
        data.update({"update_attributes": update_attributes})
    if len(remove_attributes) > 0:
        data.update({"remove_attributes": remove_attributes})

    if len(data) == 0:
        logging.error(f'no update of {hostname} needed but update_host_in_cmk called')
        return

    headers={
        "If-Match": etag,
        "Content-Type": 'application/json',
    }
    logging.debug(f'sending request {data} {headers}')
    response = check_mk.put(url=f"/objects/host_config/{hostname}", 
                             json=data,
                             headers=headers)
    if response.status_code == 200:
        logging.info('updated successfully')
    else:
        logging.error(f'status {response.status_code}; error: {response.content}')

def update_hosts(sot, sot_devices, cmk_devices, check_mk_config, do_update=True):
    """
    this devicelist is the SOT devicelist!
    """
    updates = []
    update_host_list =[]
    dry_run_data = {}
    check_mk = start_session(check_mk_config)

    for device in sot_devices:
        update_attributes = {}
        remove_attributes = []
        need_update = False
        cmk_htg = {}

        hostname = device.get('hostname')
        # build dict for dry run
        add_to_dry_run = False
        snmp_equals = True
        dry_run = {'cmk': {
                        'ip': None,
                        'snmp': None,
                        'tags': None,
                        'labels': None
                    },
                    'sot': {
                        'ip': None,
                        'snmp': None,
                        'tags': None,
                        'labels': None
                    }
                    }

        logging.debug(f'checking host {hostname}')
        if len(cmk_devices) > 0:
            host_properties = None
            etag = None
            for host in cmk_devices:
                if hostname == host.get('host_name'):
                    host_properties = host
        else:
            etag, host_properties = get_host(hostname, check_mk)

        if host_properties is None:
            logging.debug(f'unknown host {hostname}')
            continue

        # checking IP
        cmk_ip_address = host_properties.get('extensions',{}).get('attributes',{}).get('ipaddress')
        sot_ip_address = device.get('primary_ip4',{}).get('address').split('/')[0]
        logging.debug(f'cmk_ip {cmk_ip_address} sot_ip {sot_ip_address}')
        if cmk_ip_address != sot_ip_address:
            update_attributes = {'ipaddress' : sot_ip_address}
            add_to_dry_run = True
            dry_run['cmk']['ip'] = cmk_ip_address
            dry_run['sot']['ip'] = sot_ip_address
            if do_update:
                logging.info(f'IP address of host {hostname} has changed from {cmk_ip_address} to {sot_ip_address}')

        # checking SNMP settings
        cmk_snmp_settings = host_properties.get('extensions',{}).get('attributes',{}).get('snmp_community',{})
        should_be = get_snmp_credentials(sot, device, check_mk_config, args.snmp_id)
        if should_be is not None:
            for key, value in cmk_snmp_settings.items():
                if key not in should_be or value != should_be[key]:
                    snmp_equals = False
            if not snmp_equals:
                update_attributes = {'snmp_community' : should_be}
                if do_update:
                    need_update = True
                    logging.info(f'SNMP credentials of host {hostname} has changed')
        elif should_be is None and len(cmk_snmp_settings) > 0:
            # disable SNMP
            snmp_equals = False
            cmk_htg['tag_snmp_ds'] = 'no-snmp'
            cmk_htg['tag_agent'] = 'no-agent'
            if do_update:
                need_update = True
                update_attributes['tag_snmp_ds'] = 'no-snmp'
                update_attributes['tag_agent'] = 'no-agent'
                logging.info(f'SNMP credentials of host {hostname} has changed')
        elif len(cmk_snmp_settings) > 0:
            snmp_equals = False
            update_attributes = {'snmp_community' : should_be}
            if do_update:
                need_update = True
                logging.info(f'SNMP credentials of host {hostname} has changed')

        if not snmp_equals:
            dry_run['cmk']['snmp'] = cmk_snmp_settings
            dry_run['sot']['snmp'] = should_be
            add_to_dry_run = True

        # check host group tags
        cmk_attributes = host_properties.get('extensions',{}).get('attributes',{})
        ignore = check_mk_config.get('defaults', {}).get('ignore_host_tag_groups')
        update_htg = False
        # prepare the list with host tags of cmk
        for key, value in cmk_attributes.items():
            if key.startswith('tag_') and key not in ignore:
                cmk_htg[key] = value

        should_be = get_cfield_from_sot(device, 'checkmk_htg', '=', 'tag_')
        # add mappings to our should_be tags
        for mapping in check_mk_config.get('mappings',{}):
            custom_fields = device.get('custom_field_data')
            sot_field = mapping.get('sot')
            sot_value = custom_fields.get(sot_field)
            cmk_field = mapping.get('cmk')
            if sot_field and cmk_field:
                cmkf = 'tag_' + cmk_field
                logging.debug(f'mapping {sot_field} to {cmk_field}')
                should_be.update({cmkf: sot_value})

        # check if we have to add/update some host tag groups
        for key, value in should_be.items():
            if key in cmk_htg and cmk_htg[key] == value:
                logging.debug(f'tag {key} of {hostname} matches')
            else:
                need_update = True
                update_htg = True
                update_attributes[key] = value
                if do_update:
                    logging.info(f'tag {key} of {hostname} should be {value}')
        # check if we have to remove some host tag groups
        for htg in cmk_htg:
            # tag_snmp_ds and tag_agent must always be there
            if htg in ['tag_snmp_ds', 'tag_agent']:
                continue
            if htg not in should_be:
                need_update = True
                update_htg = True
                remove_attributes.append(htg)
                if do_update:
                    logging.info(f'tag {htg} of {hostname} should be removed')

        if not do_update and update_htg:
            dry_run['cmk']['tags'] = cmk_htg
            dry_run['sot']['tags'] = should_be
            add_to_dry_run = True

        # check labels
        # if there is an update we have to update ALL labels not only the changes!
        cmk_labels = host_properties.get('extensions',{}).get('attributes',{}).get('labels',{})
        should_be = get_cfield_from_sot(device, 'checkmk_labels', ':', '')
        if len(should_be) != len(cmk_labels):
            need_update = True
            update_attributes['labels'] = {}
            if do_update:
                logging.info(f'label(s) of {hostname} must be updated or removed')
        for key, value in should_be.items():
            # prepare a list that contains ALL labels
            if not 'labels' in update_attributes:
                update_attributes['labels'] = {}
            update_attributes['labels'][key] = value
            if key in cmk_labels and cmk_labels[key] != value:
                need_update = True
                if do_update:
                    logging.debug(f'label {key} of {hostname} must be {value}')

        # update_attributes contains all labels that should be in cmk
        # if no update is necessary we remove ALL labels
        if not need_update and 'labels' in update_attributes:
            del update_attributes['labels']
        if not do_update and need_update:
            dry_run['cmk']['labels'] = cmk_labels
            dry_run['sot']['labels'] = should_be
            add_to_dry_run = True

        # checking folder
        cmk_folder = host_properties.get('extensions',{}).get('folder')
        folder = get_folder_name(device, check_mk_config.get('folders',{}).get('structure',{}))
        cmk_folder = cmk_folder.replace('/','~')
        if (folder != cmk_folder):
            logging.debug(f'host {hostname} with etag {etag} is in {cmk_folder} ... should be in {folder}')
            dry_run['cmk']['folder'] = cmk_folder
            dry_run['sot']['folder'] = folder
            add_to_dry_run = True
            need_update = True
            if do_update:
               logging.info(f'host {hostname} must be moved to the new folder {folder}')
               # create folder if necessary
               update_folders([{'folder': folder}], check_mk_config, check_mk)
               activate_all_changes(check_mk_config, check_mk)
               # now move host to new folder
               move_host_to_folder(hostname, etag, folder, check_mk)

        if need_update:
            logging.info(f'{hostname} must be updated ({len(update_attributes)} / {len(remove_attributes)} / {need_update})')
            updates.append(device)
            if do_update:
                update_host_in_cmk(hostname, etag, update_attributes, remove_attributes, check_mk)

        if add_to_dry_run:
            dry_run_data[hostname] = dry_run
            update_host_list.append(device)

    if not do_update:
        return dry_run_data, update_host_list

def delete_hosts(devices, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    data = []
    for device in devices:
        data.append(device.get('host_name'))

    response = check_mk.post(url=f"/domain-types/host_config/actions/bulk-delete/invoke", json={'entries': data})
    if response.status_code == 200 or response.status_code == 204 :
        logging.info(f'hosts {data} successfully deleted')
    else:
        logging.error(f'error removing hosts; status {response.status_code}; error: {response.content}')

def get_missing_devices(sot, check_mk_config):
    global _cache_all_sot_devices
    global _cache_all_cmk_devices
    missing_devices = []

    cfg = check_mk_config.get('defaults',{}).get('sync')
    parameter = cfg.get('devices', {'name':''})
    if parameter == 'all':
        parameter = {'name': ''}

    if _cache_all_sot_devices is None:
        _cache_all_sot_devices = sot.get.query(values=['hostname', 'primary_ip4','location','custom_field_data'],
                                               where=parameter)
    if _cache_all_cmk_devices is None:
        _cache_all_cmk_devices = get_all_hosts()

    for device in _cache_all_sot_devices:
        hostname = device.get('hostname')
        if not any(d['host_name'] == hostname for d in _cache_all_cmk_devices):
            missing_devices.append(device)

    return missing_devices

def get_to_be_updated_device(sot, check_mk_config):
    global _cache_all_sot_devices
    global _cache_all_cmk_devices
    to_be_updated = []

    cfg = check_mk_config.get('defaults',{}).get('sync')
    parameter = cfg.get('devices', {'name':''})
    if parameter == 'all':
        parameter = {'name': ''}

    if _cache_all_sot_devices is None:
        _cache_all_sot_devices = sot.get.query(values=['hostname', 'primary_ip4','site','custom_fields'],
                                               where=parameter)
    if _cache_all_cmk_devices is None:
        _cache_all_cmk_devices = get_all_hosts()

    logging.info(f'there are {len(_cache_all_sot_devices)} in SOT and {len(_cache_all_cmk_devices)} in checkmk')

    return update_hosts(sot, _cache_all_sot_devices, _cache_all_cmk_devices, check_mk_config, False)

def get_to_be_removed_device(sot, check_mk_config):
    global _cache_all_sot_devices
    global _cache_all_cmk_devices
    to_be_removed = []

    cfg = check_mk_config.get('defaults',{}).get('sync')
    parameter = cfg.get('devices', {'name':''})
    if parameter == 'all':
        parameter = {'name': ''}

    if _cache_all_sot_devices is None:
        _cache_all_sot_devices = sot.get.query(values=['hostname', 'primary_ip4','site','custom_fields'],
                                               where=parameter)
    if _cache_all_cmk_devices is None:
        _cache_all_cmk_devices = get_all_hosts()

    # devices that are are no longer in our sot but in checkmk
    for device in _cache_all_cmk_devices:
        hostname = device.get('host_name')
        if not any(d['hostname'] == hostname for d in _cache_all_sot_devices):
            to_be_removed.append(device)

    return to_be_removed

def repair_services(check_mk_config, check_mk=None):

    if check_mk is None:
        check_mk = start_session(check_mk_config)

    devices = get_all_hosts()
    hosts_with_no_services = []
    for device in devices:
        hostname = device.get('host_name')
        params={
            "query": '{"op": "=", "left": "host_name", "right": "' + hostname + '"}',
            "columns": ['host_name', 'description'],
        }
        response = check_mk.get(url=f"/objects/host/{hostname}/collections/services", params=params)
        if response.status_code == 200 and len(response.json()['value']) <= 2:
            logging.info(f'host {hostname} has only {len(response.json()["value"])} services')
            hosts_with_no_services.append({'host_name': hostname})
    
    if len(hosts_with_no_services) > 0:
        start_single_discovery(check_mk_config, hosts_with_no_services, check_mk)

def show(sot, check_mk_config, what, check_mk=None):
    if check_mk is None:
        check_mk = start_session(check_mk_config)

    if 'discovery' == what:
        response = check_mk.get(url=f"/objects/discovery_run/bulk_discovery")
        if response.status_code == 200:
            data = response.json()
            for i in data['extensions']['logs']['progress']:
                print(i)
        elif response.status_code == 204:
            print("Done")
        else:
            raise RuntimeError(pprint.pformat(response.json()))
    elif 'missing-devices' == what:
        parameter = {'name': ''}
        sot_devicelist = sot.get.query(values=['hostname', 'primary_ip4','site','custom_fields'],
                                       where=parameter)
        cmk_devicelist = get_all_hosts()
        print(f'sot: {len(sot_devicelist)} cmk {len(cmk_devicelist)}')
        for device in sot_devicelist:
            hostname = device.get('hostname')
            if not any(d['host_name'] == hostname for d in cmk_devicelist):
                print(hostname)

    elif 'rules' in what:
        remove_links = False
        use_value = False
        rules = what.split('=')[1]
        if rules == 'hg':
            rules = 'host_groups'
        elif rules == 'sg':
            rules = 'service_groups'
        elif rules == 'hcc':
            remove_links = True
            use_value = True
            rules = 'host_check_commands'
        elif rules == 'chkgrp_if':
            remove_links = True
            use_value = True
            rules = 'checkgroup_parameters:if'
        elif rules == "iir":
            remove_links = True
            use_value = True
            rules = 'inventory_if_rules'
        params={"ruleset_name": rules}
        response = check_mk.get(url=f"/domain-types/rule/collections/all", params=params)
        if response.status_code == 200:
            if use_value:
                data = response.json()['value']
            else:
                data = response.json()
            if remove_links:
                if isinstance(data, list):
                    for i in data:
                        if 'links' in i:
                            del i['links']
                elif isinstance(data, dict):
                    if 'links' in data:
                        del data['links']
            print(json.dumps(data, indent=4))
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif 'rule' in what:
        rule = what.split('=')[1]
        response = check_mk.get(url=f"/objects/rule/{rule}")
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif 'host' in what:
        host = what.split('=')[1]
        params={"effective_attributes": False}
        response = check_mk.get(url=f"/objects/host_config/{host}", params=params)
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
            headers = response.headers
            print(f'ETag: {headers.get("ETag")}')
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif 'htg' in what:
        response = check_mk.get(url=f"/domain-types/host_tag_group/collections/all")
        if response.status_code == 200:
            data = response.json()['value']
            for i in data:
                if 'links' in i:
                    del i['links']
                if 'members' in i:
                    del i['members']
            print(json.dumps(data, indent=4))
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif 'folder' in what:
        folder = what.split('=')[1]
        params={"show_hosts": False}
        response = check_mk.get(url=f"/objects/folder_config/{folder}", params=params)
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
            headers = response.headers
            print(f'ETag: {headers.get("ETag")}')
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif 'no-services' in what:
        devices = get_all_hosts()
        hosts_with_no_services = []
        for device in devices:
            hostname = device.get('host_name')
            params={
                "query": '{"op": "=", "left": "host_name", "right": "' + hostname + '"}',
                "columns": ['host_name', 'description'],
            }
            response = check_mk.get(url=f"/objects/host/{hostname}/collections/services", params=params)
            if response.status_code == 200 and len(response.json()['value']) <= 2:
                logging.info(f'host {hostname} has only {len(response.json()["value"])} services')
                hosts_with_no_services.append(hostname)
    elif 'services' in what:
        host = what.split('=')[1]
        params={
            "query": '{"op": "=", "left": "host_name", "right": "' + host + '"}',
            "columns": ['host_name', 'description'],
        }
        response = check_mk.get(url=f"/objects/host/{host}/collections/services", params=params)
        if response.status_code == 200:
            data = response.json()['value']
            for i in data:
                del i['links']
            print(json.dumps(data, indent=4))
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    sot_devicelist = []
    cmk_devicelist = []

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="check_mk config file")
    # what devices
    parser.add_argument('--devices', type=str, required=False, help="query to get list of devices")
    parser.add_argument('--snmp-id', type=str, required=False, help="Overwrite SNMP config and use SNMP-ID instead")
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
    #parser.add_argument('--no-discovery', action='store_false', help='Do not discover host after adding it')
    #parser.add_argument('--no-activation', action='store_false', help='Do not activate changes')
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
    
    # the basic stuff at the beginning
    if args.add_default_folders:
        add_default_folders(check_mk_config)
    
    if args.add_host_groups:
        add_config_to_checkmk(check_mk_config.get('host_groups',[]), 
                              '/domain-types/host_group_config/collections/all', 
                              'host groups')
    if args.add_host_tag_groups:
        add_host_tag_groups(sot, check_mk_config.get('host_tag_groups',[]))

    if args.add_rules:
        add_config_to_checkmk(check_mk_config.get('rules',[]), 
                              '/domain-types/rule/collections/all', 
                              'rules')

    # now look at the devices
    if args.devices and (args.add_hosts or args.update_hosts or args.add_folders or args.update_cmk):
        sot_devicelist = sot.select('hostname', 'primary_ip4', 'location', 'cf_snmp_credentials') \
                     .using('nb.devices') \
                     .normalize(False) \
                     .where(args.devices)
        
        for device in sot_devicelist:
            hostname = device.get('hostname')
            logging.debug(f'adding hostname: {hostname}')
        logging.info(f'added {len(sot_devicelist)} hosts to our list of devices')
    elif args.devices and (args.service_discovery or args.repair_services or args.delete_hosts):
        # and in this case we use the checkmk database to get the devices
        devices = get_all_hosts()
        for device in devices:
            hostname = device.get('host_name')
            key, value = args.devices.split('=')
            if key == 'name':
                if value in hostname:
                    cmk_devicelist.append({'host_name': hostname})
            elif key == 'folder':
                if device.get('folder').startswith(value):
                    cmk_devicelist.append({'host_name': hostname,
                                           'folder': device.get('folder')})
        logging.info(f'added {len(cmk_devicelist)} hosts to our list of devices')

    if args.add_hosts:        
        devices_to_add = build_list(sot, sot_devicelist, args.snmp_id, check_mk_config)
        if len(devices_to_add) > 0:
            if args.add_folders:
                update_folders(devices_to_add, check_mk_config)
            # now add host
            add_to_check_mk(devices_to_add)
    elif args.update_hosts:
        update_hosts(sot, sot_devicelist, [], check_mk_config, True)
    elif args.add_folders and not args.add_hosts:
        devices = []
        for device in sot_devicelist:
            devices.append(prepare_host_data(sot, device, check_mk_config, args.snmp_id))
        update_folders(devices, check_mk_config)
    elif args.show:
        show(sot, check_mk_config, args.show)
    # the following calls use the checkmk_devicelist
    elif args.delete_hosts:
        delete_hosts(cmk_devicelist)
    """
    sync checkmk
     - sync: add missing, update existing and remove devices
     - massing: add missing devices (devices that are in our sot but not in checkmk) to checkmk
     - update: update all hosts in checkmk
     - remove: remocve devices thar are not in our sot (anymore) but in checkmk
    """
    if args.missing_cmk or args.sync:
        missing_devices = get_missing_devices(sot, check_mk_config)
        if args.dry_run:
            print(f'{len(missing_devices)} are missing in checkmk (cmk: {len(_cache_all_cmk_devices)} sot: {len(_cache_all_sot_devices)})')
            for device in missing_devices:
                print(f'{device.get("hostname")}')
        elif len(missing_devices) > 0:
            logging.info(f'adding {len(missing_devices)} to check_mk')
            devices_to_add = build_list(sot, missing_devices, None, check_mk_config)
            if len(devices_to_add) > 0:
                update_folders(devices_to_add, check_mk_config)
                add_to_check_mk(devices_to_add)
    if args.remove_cmk or args.sync:
        to_be_removed = get_to_be_removed_device(sot, check_mk_config)
        if args.dry_run:
            print(f'There are {len(to_be_removed)} devices that must be removed in checkmk (cmk: {len(_cache_all_cmk_devices)} sot: {len(_cache_all_sot_devices)})')
            for device in to_be_removed:
                print(f'{device.get("host_name")}')
        elif len(to_be_removed) > 0:
            logging.info(f'removing {len(to_be_removed)} devices in check_mk')
            delete_hosts(to_be_removed)
    if args.update_cmk or args.sync:
        dry_run_data, to_be_updated = get_to_be_updated_device(sot, check_mk_config)
        if args.dry_run:
            #print(json.dumps(dry_run_data, indent=4))
            print(f'{len(to_be_updated)} host be be updated')
        else:
            logging.info(f'updating {len(to_be_updated)} devices in check_mk')
            update_hosts(sot, to_be_updated, [], check_mk_config, True)

    """
    start service discovery or repair services
    """

    if args.service_discovery:
        if args.add_hosts:
            activate_all_changes(check_mk_config)
            start_discovery(check_mk_config, devices_to_add, None, False)
        else:
            start_discovery(check_mk_config, cmk_devicelist, None, False)
    elif args.repair_services:
        repair_services(check_mk_config)

    # and now we need both list
    if args.activate_changes:
        activate_all_changes(check_mk_config)

