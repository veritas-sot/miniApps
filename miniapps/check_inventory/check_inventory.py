#!/usr/bin/env python

import argparse
import os
import urllib3
import xlsxwriter
import sys
from loguru import logger

import veritas.logging
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
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    parser.add_argument('--filename', type=str, required=True, help="input file")
    parser.add_argument('--out', type=str, required=False, help="output file")
    parser.add_argument('--format', type=str, required=False, help="format (text, csv, excel)")

    args = parser.parse_args()

    # read config
    check_config = tools.get_miniapp_config('check_inventory', BASEDIR, args.config)
    if not check_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=check_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='check_inventory',
        uuid=args.uuid)

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
            logger.info(f'{hostname} not found')
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
            logger.debug(f'table_coordinations={table_coordinations}')
            for c in header_data:
                header.append({'header': c})
            worksheet.add_table(table_coordinations, {'data': missing, 
                                                      'header_row': True, 
                                                      'columns': header
                                                     })
            worksheet.autofit()
            workbook.close()


