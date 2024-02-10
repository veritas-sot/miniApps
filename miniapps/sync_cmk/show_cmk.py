#!/usr/bin/env python

import argparse
import urllib3
import pprint
import json
import os
import sys
from loguru import logger

import veritas.logging
from veritas.tools import tools
from veritas.checkmk import checkmk
from veritas.sot import sot as sot


def show(sot, checkmk_config, args):
    cmk = checkmk.Checkmk(sot=sot, 
                          url=checkmk_config.get('check_mk',{}).get('url'),
                          site=checkmk_config.get('check_mk',{}).get('site'),
                          username=checkmk_config.get('check_mk',{}).get('username'),
                          password=checkmk_config.get('check_mk',{}).get('password'))
    if args.discovery:
        response = cmk.get(url='/objects/discovery_run/bulk_discovery')
        if response.status_code == 200:
            data = response.json()
            for i in data['extensions']['logs']['progress']:
                print(i)
        elif response.status_code == 204:
            print("Done")
        else:
            raise RuntimeError(pprint.pformat(response.json()))
    elif args.missing_devices:
        sot_devicelist = sot.select('hostname, primary_ip4, location, custom_fields') \
                            .using('nb.devices') \
                            .where()
        cmk_devicelist = cmk.get_all_hosts()
        print(f'sot: {len(sot_devicelist)} cmk {len(cmk_devicelist)}')
        for device in sot_devicelist:
            hostname = device.get('hostname')
            if not any(d['host_name'] == hostname for d in cmk_devicelist):
                print(hostname)

    elif args.rules:
        rules = args.rules
        remove_links = False
        use_value = False
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
        response = cmk.get(url="/domain-types/rule/collections/all", params=params)
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
    elif args.rule:
        rule = args.rule
        response = cmk.get(url=f"/objects/rule/{rule}")
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif args.host:
        host = args.host
        params={"effective_attributes": False}
        response = cmk.get(url=f"/objects/host_config/{host}", params=params)
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
            headers = response.headers
            print(f'ETag: {headers.get("ETag")}')
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif args.htg:
        response = cmk.get(url="/domain-types/host_tag_group/collections/all")
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
    elif args.folder:
        folder = args.folder
        params={"show_hosts": False}
        response = cmk.get(url=f"/objects/folder_config/{folder}", params=params)
        if response.status_code == 200:
            data = response.json()
            del data['links']
            print(json.dumps(data, indent=4))
            headers = response.headers
            print(f'ETag: {headers.get("ETag")}')
        else:
            data = response.json()
            print(f'status {response.status_code} detail: {data["detail"]}')
    elif args.no_services:
        devices = cmk.get_all_hosts()
        hosts_with_no_services = []
        for device in devices:
            hostname = device.get('host_name')
            params={
                "query": '{"op": "=", "left": "host_name", "right": "' + hostname + '"}',
                "columns": ['host_name', 'description'],
            }
            response = cmk.get(url=f"/objects/host/{hostname}/collections/services", params=params)
            if response.status_code == 200 and len(response.json()['value']) <= 2:
                logger.info(f'host {hostname} has only {len(response.json()["value"])} services')
                hosts_with_no_services.append(hostname)
    elif args.services:
        host = args.services
        params={
            "query": '{"op": "=", "left": "host_name", "right": "' + host + '"}',
            "columns": ['host_name', 'description'],
        }
        response = cmk.get(url=f"/objects/host/{host}/collections/services", params=params)
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
    # status
    parser.add_argument('--discovery', action='store_true', required=False, help="show discovery")
    parser.add_argument('--missing-devices', action='store_true', required=False, help="show missing devices")
    parser.add_argument('--rules', type=str, required=False, help="show rules")
    parser.add_argument('--rule', type=str, required=False, help="show rules")
    parser.add_argument('--host', type=str, required=False, help="show host")
    parser.add_argument('--htg', action='store_true', required=False, help="show host tag groups")
    parser.add_argument('--folder', type=str, required=False, help="show folder")
    parser.add_argument('--no-services', action='store_true', required=False, help="show hosts without services")
    parser.add_argument('--services', type=str, required=False, help="show services")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    cmk_config = tools.get_miniapp_config('sync_cmk', BASEDIR, args.config)
    if not cmk_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=cmk_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='sync_cmk',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=cmk_config['sot']['token'],
                  ssl_verify=cmk_config['sot'].get('ssl_verify', False),
                  url=cmk_config['sot']['nautobot'])

    show(sot, cmk_config, args)
