#!/usr/bin/env python

import argparse
import urllib3
import os

# veritas
import veritas.logging
import playbook
from veritas.sot import sot as veritas_sot
from veritas.tools import tools
from exporter import export as export_main
from updater import update as update_main
from transformer import transform as transform_main
from importer import import_data as import_main

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
    parser_update = subparsers.add_parser('update', help='update devices')
    parser_export = subparsers.add_parser('export', help='export data of devices')
    parser_import = subparsers.add_parser('import', help='import data to nautobot')
    parser_transform = subparsers.add_parser('transform', help='transform properties of devices')

    #
    # updater
    #
    # this parameter is only used in if --update was set
    parser_update.add_argument('--filename', type=str, required=True, help="name of file to update data")
    parser_update.add_argument('--job', type=str, required=False, help="job to run")
    parser_update.add_argument('--where', type=str, required=False, help="overwrite where statement")
    parser_update.add_argument('--force', action='store_true', help='force bulk updates even if checksum equals')
    parser_update.add_argument('--dry-run', action='store_true', help='print updates only')
    parser_update.add_argument('--add-missing-data', action='store_true', help='add missing data if possible (eg. IP-address)')

    #
    # exporter
    #
    group_exporter = parser_export.add_mutually_exclusive_group(required=True)
    parser_export.add_argument('--playbook', type=str, required=True, help="playbook config to use")
    parser_export.add_argument('--job', type=str, required=True, help="job to run")
    group_exporter.add_argument('--profile', type=str, required=False, help="profile to get login credentials")
    group_exporter.add_argument('--username', type=str, required=False, help="login username")
    group_exporter.add_argument('--password', type=str, required=False, help="login password")

    #
    # importer
    #

    parser_import.add_argument('--filename', type=str, required=False, help="name of file to transform data")
    parser_import.add_argument('--device', type=str, required=False, help="name of file to import device")
    parser_import.add_argument('--dry-run', action='store_true', help='print updates only')

    #
    # transformer
    #
    parser_transform.add_argument('--filename', type=str, required=True, help="name of file to transform data")
    parser_transform.add_argument('--job', type=str, required=False, help="job to run")
    parser_transform.add_argument('--where', type=str, required=False, help="overwrite where statement")   
    parser_transform.add_argument('--template', type=str, default="", required=False, help="template to use to update value")
    parser_transform.add_argument('--dry-run', action='store_true', help='print updates only')

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    kobold_config = tools.get_miniapp_config('kobold', BASEDIR, args.config)
    if not kobold_config:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=kobold_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='kobold',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=kobold_config['sot']['token'],
                          ssl_verify=kobold_config['sot'].get('ssl_verify', False),
                          url=kobold_config['sot']['nautobot'],
                          debug=args.debug_veritas)

    if args.command == 'export':
        pb = playbook.Playbook(sot=sot, playbook=args.playbook)
        export_main(sot, pb, args)
    elif args.command == 'import':
        import_main(sot, args)
    elif args.command == 'update':
        update_main(sot, args, kobold_config)
    elif args.command == 'transform':
        transform_main(sot, args, kobold_config)

if __name__ == "__main__":
    main()
