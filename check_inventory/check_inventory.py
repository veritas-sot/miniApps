#!/usr/bin/env python

import argparse
import logging
import yaml
import os
import json
import urllib3
from veritas.sot import sot
from veritas.tools import tools


BASEDIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_CONFIG_FILE = "./check_inventory.yaml"

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    devicelist = []
    missing = []
    number_of_missing_devices = 0
    number_of_found_devices = 0

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="set_snmp config file")
    parser.add_argument('--filename', type=str, required=True)
    parser.add_argument('--out', type=str, required=False)
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="set_snmp loglevel")

    args = parser.parse_args()

    # read set_snmp config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = DEFAULT_CONFIG_FILE

    with open(config_file) as f:
        check_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(check_config, ['set_snmp', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(check_config, ['set_snmp', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(check_config, ['set_snmp', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=check_config['sot']['token'], 
                  url=check_config['sot']['nautobot'],
                  ssl_verify=check_config['sot'].get('ssl_verify', False))

    column_mapping = check_config.get('mappings',{}).get('columns',{})
    table = tools.read_excel_file(args.filename)
    for row in table:
        d = {}
        for k,v in row.items():
            key = column_mapping.get(k) if k in column_mapping else k
            d[key] = v
        devicelist.append(d)
    
    for device in devicelist:
        hostname = device.get('hostname').lower()
        hostname = hostname.split(' ')[0]
        id = sot.get.id(item='device', name=hostname)
        if not id:
            logging.info(f'{hostname} not found')
            number_of_missing_devices += 1
            missing.append(device)
        else:
            number_of_found_devices += 1
    
    print(f'found {number_of_found_devices} hosts; {number_of_missing_devices} are missing')
    for m in missing:
        print(m.get('hostname'))

    if args.out:
        with open(args.out, 'w') as f:
            for m in missing:
                f.write(m.get('hostname'))
                f.write('\n')

