#!/usr/bin/env python

import argparse
import logging
import urllib3
import yaml
from veritas.tools import tools
from veritas.checkmk import checkmk
from veritas.sot import sot as sot


default_config_file = "cmk.yaml"


def add_default_folders(checkmk_config):

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    for folder in check_mk_config.get('folders',{}).get('init',[]):
        name = folder.get('name')
        parent = folder.get('parent')
        data = {"name": name,
                "title": folder.get('title', name),
                "parent": parent
               }
        folder_config = cmk.get_folder_config(check_mk_config, name)
        success = cmk.add_folder(folder_config)
        if success:
            print(f'folder {name} successfully created in cmk')
        else:
            print(f'could not create folder {name} in cmk')

def add_config_to_checkmk(checkmk_config, url, title):

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    for item in checkmk_config:
        title = item.get('value_raw', title)
        logging.debug(f'adding {title}')
        success = cmk.add_config(item, url, title)
        if success:
            print(f'added config {title} successfully')
        else:
            print(f'could not add config {title} to cmk')

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

    # now add host tag groups to cmk
    add_config_to_checkmk(host_tag_groups, '/domain-types/host_tag_group/collections/all', 'host tag groups')   


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
    parser.add_argument('--add-host-tag-groups', action='store_true', help='Add host tag groups')
    parser.add_argument('--add-host-groups', action='store_true', help='Add host groups')
    parser.add_argument('--add-rules', action='store_true', help='Add rules to checkmk')
    parser.add_argument('--add-default-folders', action='store_true', help='Add default folders')
    parser.add_argument('--add-folders', action='store_true', help='Add folder if missing')
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
