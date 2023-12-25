#!/usr/bin/env python

import argparse
import os
import json
import csv
import yaml
import urllib3
from loguru import logger
from pathlib import Path
from openpyxl import load_workbook
from veritas.sot import sot as sot
from veritas.tools import tools

# set default config file to your needs
default_config_file = "./conf/updater.yaml"


def build_dict(value, my_dict, keys):
    if isinstance(keys, list):
        my_dict[keys[0]] = build_dict(value, my_dict, keys[1])
    else:
        return {keys: value}
    return my_dict

def parse_row(row, key_mapping, value_mapping):
    data = {}

    for k, value in row.items():
        if k in key_mapping:
            key = key_mapping.get(k)
        else:
            key = k
        # value_mappings are uses to 'rename' values
        if value_mapping:
            mapping = value_mapping.get(key, {})
            for map_key,map_value in mapping.items():
                if value == map_key:
                    value = map_value

        if key.startswith('cf_'):
            if 'custom_fields' not in data:
                data['custom_fields'] = {}
            data['custom_fields'][key.split('cf_')[1]] = value
        elif '__' in key:
            # check if key has subkeys
            path = key.split('__')
            d = build_dict(value, {}, path)
            if path[0] == 'interfaces':
                data.update(d[path[0]])
            else:
                if path[0] not in data:
                    data[path[0]] = {}
                data[path[0]].update(d[path[0]])
        else:
            data[key] = value
    return data

def read_csv(filename, updater_config, key_mapping={}, value_mapping={}):
    contains_interface = False
    data = []

    delimiter = updater_config['defaults']['import'].get('delimiter',',')
    quotechar = updater_config['defaults']['import'].get('quotechar','|')
    quoting_cf = updater_config['defaults']['import'].get('quoting','minimal')
    newline = updater_config['defaults']['import'].get('newline','')
    if quoting_cf == "none":
        quoting = csv.QUOTE_NONE
    elif quoting_cf == "all":
        quoting = csv.QUOTE_ALL
    elif quoting_cf == "nonnumeric":
        quoting = csv.QUOTE_NONNUMERIC
    else:
        quoting = csv.QUOTE_MINIMAL
    logger.info(f'reading {filename} delimiter={delimiter} quotechar={quotechar} newline={newline} quoting={quoting_cf}')

    # read CSV file
    with open(filename, newline=newline) as csvfile:
        csvreader = csv.DictReader(csvfile, 
                                   delimiter=delimiter, 
                                   quoting=quoting,
                                   quotechar=quotechar)
        for row in csvreader:
            # check if we have interfaces to update or import
            for name in row:
                if 'interface' in name:
                    contains_interface = True

            old_checksum = new_checksum = 0
            if 'checksum' in row:
                old_checksum = row['checksum']
                del row['checksum']
                new_checksum = tools.calculate_md5(list(row.values()))
                logger.debug(f'old_checksum: {old_checksum} new_checksum: {new_checksum}')

            row['checksum'] = old_checksum == new_checksum
            data.append(parse_row(row, key_mapping, value_mapping))

    return contains_interface, data

def read_xlsx(filename, key_mapping={}, value_mapping={}):
    contains_interface = False
    data = []
    table = []

    # Load the workbook
    workbook = load_workbook(filename)
    # Select the active worksheet
    worksheet = workbook.active
    
    # loop through table and build list of dict
    rows = worksheet.max_row
    # the +1 is important otherwise we miss the the last column (eg. checksum)
    columns = worksheet.max_column +1 
    for row in range(2, rows + 1):
        line = {}
        for col in range(1, columns):
            key = worksheet.cell(row=1, column=col).value
            value = worksheet.cell(row=row, column=col).value
            line[key] = value
        table.append(line)

    for row in table:
        old_checksum = new_checksum = 0
        contains_interface = any(d.startswith('interface') for d in row.keys())
        if any(d == 'checksum' for d in row.keys()):
            old_checksum = row['checksum']
            del row['checksum']
            new_checksum = tools.calculate_md5(list(row.values()))
            logger.debug(f'old_checksum: {old_checksum} new_checksum: {new_checksum}')

        row['checksum'] = old_checksum == new_checksum
        data.append(parse_row(row, key_mapping, value_mapping))
    logger.debug(f'contains_interface={contains_interface}')
    return contains_interface, data

def bulk_update(sot, data, updater_config, endpoint):
    nb = sot.rest(url=updater_config['sot']['nautobot'], token=updater_config['sot']['token'])
    nb.session()
    response = nb.patch(url=f"api/{endpoint}/", json=data)
    if response.status_code != 200:
        logger.error(f'could not update data; got error {response.content}')
    else:
        logger.info(f'data updated')

if __name__ == "__main__":
    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="updater config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    parser.add_argument('--filename', type=str, required=True, help="data to update")
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
    tools.create_logger_environment(updater_config, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=updater_config['sot']['token'],
                  ssl_verify=updater_config['sot'].get('ssl_verify', False),
                  url=updater_config['sot']['nautobot'],
                  git=None)

    # get mapping from config
    key_mapping = updater_config.get('mappings',{}).get('keys',{})
    value_mapping = updater_config.get('mappings',{}).get('valaues',{})

    if 'csv' in args.filename:
        contains_interface, data = read_csv(args.filename, updater_config, key_mapping, value_mapping)
    elif 'xlsx' in args.filename:
        contains_interface, data = read_xlsx(args.filename, key_mapping, value_mapping)

    # Data without modification does not need to be changed unless the user wants it.
    updates = []
    for row in data:
        if not row['checksum'] or args.force:
            updates.append(row)

    logger.info(f'{len(updates)} to be updated force={args.force} interfaces: {contains_interface}')
    if len(updates) > 0:
        # are we able to make a bulk update by using the ID?
        if 'id' in updates[0]:
            if contains_interface:
                bulk_update(sot, updates, updater_config, "dcim/interfaces")
            else:
                bulk_update(sot, updates, updater_config, "dcim/devices")
        else:
            # we do not have an ID; use hostname/interface name instead
            if contains_interface:
                for interface in updates:
                    sot.device(interface['hostname']).interface(interface['name']).update(interface)
            else:
                for device in updates:
                    sot.device(device['hostname']).update(device)
