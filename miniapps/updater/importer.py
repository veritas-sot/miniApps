#!/usr/bin/env python

import argparse
import os
import json
import csv
import yaml
import urllib3
import sys
from loguru import logger
from pathlib import Path
from openpyxl import load_workbook

import veritas.logging
from veritas.sot import sot as sot
from veritas.tools import tools


def read_json(filename):
    data = []
    logger.debug(f'reading HLDM from {filename}')
    with open(filename, 'r') as f:
        data.append(json.load(f))

    return data

def prepare_new_data(args, sot, defaults, new_data):
    device_defaults = {}
    data = []

    for item in new_data:
        if 'name' in item:
            hostname = item.get('name').lower()
            del item['name']
        else:
            raise Exception('need hostname to add data')

        field = None
        if 'primary_ip' in item:
            field = 'primary_ip'
        elif 'primary_ip4' in item:
            field = 'primary_ip4'
        else:
            raise Exception('need IP address to add data')

        # the used IP address is stored in 'primary_ip4
        primary_ip = item.get(field)
        del item[field]
        item['primary_ip4'] = primary_ip

        device_defaults = get_device_defaults(defaults, primary_ip)
        device_properties = {
            "name": hostname,
            "site": {'slug': slugify(device_defaults.get('site'))},
            "device_role": {'slug': slugify(device_defaults.get('device_role'))},
            "device_type": {'slug': slugify(device_defaults.get('device_type'))},
            "manufacturer": {'slug': slugify(device_defaults.get('manufacturer'))},
            "platform": {'slug': slugify(device_defaults.get('platform'))},
            "status": device_defaults.get('status','active'),
            "custom_fields": device_defaults.get('custom_fields',{})
        }

        # customfields are special; we have to merge the dict
        if 'custom_fields' in item:
            cfields = item['custom_fields']
            del item['custom_fields']

        # overwrite existing values with import
        device_properties.update(item)
        # and add custom fields of the item
        for key, value in cfields.items():
            device_properties['custom_fields'][key] = value
        data.append(device_properties)

    return data

def import_device(sot, device_properties):

    interface_ip_addresses = {}
    interfaces = device_properties.get('interfaces')
    config_context = device_properties.get('config_context')
    primary_ip4 = device_properties.get('primary_ip4')
    del device_properties['interfaces']
    del device_properties['config_context']
    del device_properties['primary_ip4']

    # we have to modify the interfaces
    for interface in interfaces:
        ip_addresses = interface.get('ip_addresses')
        # type and mode are lower case
        if 'type' in interface:
            interface['type'] = interface['type'].lower()
        if 'mode' in interface and interface['mode']:
            interface['mode'] = interface['mode'].lower()
        # 'lag' must not be null
        if 'lag' in interface and not interface['lag']:
            del interface['lag']
        # save IP address
        if 'ip_addresses' in interface and len(interface['ip_addresses']) > 0:
            interface_ip_addresses[interface['name']] = interface['ip_addresses']

    new_device = sot.onboarding \
        .interfaces(interfaces) \
        .add_prefix(True) \
        .add_device(device_properties)

if __name__ == "__main__":
    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', default="importer.yaml", type=str, required=False, help="importer config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    parser.add_argument('--filename', type=str, required=True, help="data to import")
    parser.add_argument('--force', action='store_true', help='force update even if checksum is equal')

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    updater_config = tools.get_miniapp_config('updater', BASEDIR, args.config)
    if not updater_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=updater_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='importer',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=updater_config['sot']['token'],
                  ssl_verify=updater_config['sot'].get('ssl_verify', False),
                  url=updater_config['sot']['nautobot'])

    if args.filename:
        device_hldm = read_json(args.filename)
        import_device(sot, device_hldm[0])
    
