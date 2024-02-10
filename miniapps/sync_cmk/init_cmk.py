#!/usr/bin/env python

import argparse
import urllib3
import os
import sys
from loguru import logger

import veritas.logging
from veritas.tools import tools
from veritas.checkmk import checkmk
from veritas.sot import sot as sot


def add_default_folders(checkmk_config):

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    for folder in checkmk_config.get('folders',{}).get('init',[]):
        name = folder.get('name')
        parent = folder.get('parent')
        data = {"name": name,
                "title": folder.get('title', name),
                "parent": parent
               }
        success = cmk.add_folder(data, 
                                 checkmk_config.get('folders',{}).get('config',[]))
        if success:
            print(f'folder {name} successfully created in cmk')
        else:
            print(f'could not create folder {name} in cmk')

def add_config_to_checkmk(checkmk_config, config, url, title):

    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))

    for item in config:
        title = item.get('value_raw', title)
        logger.debug(f'adding {title}')
        success = cmk.add_config(item, url)
        if success:
            print(f'added config {title} successfully')
        else:
            print(f'could not add config {title} to cmk')

def add_host_tag_groups(sot, checkmk_config, host_tag_groups):
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
                    if 'set' not in cfields:
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
    add_config_to_checkmk(checkmk_config, 
                          host_tag_groups, 
                          '/domain-types/host_tag_group/collections/all', 'host tag groups')   

if __name__ == "__main__":

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
    # what to do
    parser.add_argument('--add-host-tag-groups', action='store_true', help='Add host tag groups')
    parser.add_argument('--add-host-groups', action='store_true', help='Add host groups')
    parser.add_argument('--add-rules', action='store_true', help='Add rules to checkmk')
    parser.add_argument('--add-default-folders', action='store_true', help='Add folders')
    parser.add_argument('--dry-run', action='store_true', help='Just print what to do')

    # parse arguments
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
    sot = sot.Sot(token=check_mk_config['sot']['token'],
                  ssl_verify=check_mk_config['sot'].get('ssl_verify', False),
                  url=check_mk_config['sot']['nautobot'])
    
    if args.add_default_folders:
        add_default_folders(check_mk_config)
    
    if args.add_host_groups:
        add_config_to_checkmk(check_mk_config,
                              check_mk_config.get('host_groups',[]), 
                              '/domain-types/host_group_config/collections/all', 
                              'host groups')
    if args.add_host_tag_groups:
        add_host_tag_groups(sot, 
                            check_mk_config,
                            check_mk_config.get('host_tag_groups',[]))

    if args.add_rules:
        add_config_to_checkmk(check_mk_config,
                              check_mk_config.get('rules',[]), 
                              '/domain-types/rule/collections/all', 
                              'rules')
