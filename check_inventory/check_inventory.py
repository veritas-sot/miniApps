#!/usr/bin/env python

import argparse
import logging
import yaml
import os
import json
import urllib3
import xlsxwriter
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
    parser.add_argument('--filename', type=str, required=True, help="input file")
    parser.add_argument('--out', type=str, required=False, help="output file")
    parser.add_argument('--format', type=str, required=False, help="format (text, csv, excel)")
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
        id = sot.get.device(hostname)
        if not id:
            logging.info(f'{hostname} not found')
            number_of_missing_devices += 1
            row = []
            for d in device:
                row.append(device[d])
            missing.append(row)
        else:
            number_of_found_devices += 1

    print(f'found {number_of_found_devices} hosts; {number_of_missing_devices} are missing')
    for m in missing:
        print(m)

    if args.out:
        if args.format == "text":
            with open(args.out, 'w') as f:
                for m in missing:
                    f.write(m.get('hostname'))
                    f.write('\n')
        elif args.format == "excel":
            table_start_col = 65 # 65=A
            table_start_row = 1
            header = []
            workbook = xlsxwriter.Workbook(args.out)
            worksheet = workbook.add_worksheet()
            header_data = devicelist[0].keys()
            number_of_cols = len(header_data)
            table_coordinations = '%s%s:%s%s' % (chr(table_start_col),
                                                 table_start_row,
                                                 chr(table_start_col + len(header_data) - 1),
                                                 table_start_row + (len(missing) ))
            logging.debug(f'table_coordinations={table_coordinations}')
            for c in header_data:
                header.append({'header': c})
            worksheet.add_table(table_coordinations, {'data': missing, 
                                                      'header_row': True, 
                                                      'columns': header
                                                     })
            worksheet.autofit()
            workbook.close()


