#!/usr/bin/env python

import argparse
import urllib3
import os

# veritas
import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools
from link import set_link
from latency import set_latency
from snmp_credentials import set_snmp_credentials


def main(args_list=None):
    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="updater config file")
    parser.add_argument('--debug-veritas', action='store_true', help='enable veritas debug logging')

    # add subparsers
    subparsers = parser.add_subparsers(dest='command')
    parser_latency = subparsers.add_parser('latency', help='check latency and write it to sot')
    parser_snmp = subparsers.add_parser('snmp', help='check SNMP credentials and write it to sot')
    parser_link = subparsers.add_parser('link', help='check link and write it to sot')

    #
    # latency
    #
    # what devices
    parser_latency.add_argument('--devices', type=str, default="", required=True, help="query to get list of devices")
    parser_latency.add_argument('--update', action='store_true', help='Update latency even if it set')

    #
    # SNMP
    #
    parser_snmp.add_argument('--devices', type=str, required=False, help="query to get list of devices")
    parser_snmp.add_argument('--update', action='store_true', help='Update credentials even if it exists')
    parser_snmp.add_argument('--exclude', type=str, help='Simple name filter to exclude devices')
    parser_snmp.add_argument('--use', type=str, default='', help='Only use specific SNMP credentials')
    # number of threads
    parser_snmp.add_argument('--threads', type=int, default=10, help='Number of threads')

    #
    # link
    #
    parser_link.add_argument('--devices', type=str, default="", required=False, help="query to get list of devices")
    parser_link.add_argument('--update', action='store_true', help='Update LINK even if it set')

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    check_and_set_config = tools.get_miniapp_config('check_and_set', BASEDIR, args.config)
    if not check_and_set_config:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=check_and_set_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='kobold',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=check_and_set_config['sot']['token'],
                          ssl_verify=check_and_set_config['sot'].get('ssl_verify', False),
                          url=check_and_set_config['sot']['nautobot'],
                          debug=args.debug_veritas)

    if args.command == 'latency':
        set_latency(sot, check_and_set_config.get('latency',{}), args.update, args.devices)
    elif args.command == 'snmp':
        set_snmp_credentials(sot, check_and_set_config.get('snmp_credentials',{}), 
                             args.exclude, args.devices, args.use, args.threads, args.update)
    elif args.command == 'link':
        set_link(sot, check_and_set_config.get('link',{}), args.update, args.devices)


if __name__ == "__main__":
    main()
