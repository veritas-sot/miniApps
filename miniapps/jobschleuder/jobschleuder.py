#!/usr/bin/env python

import argparse
import urllib3
import os

# veritas
import registry
import worker
import scheduler_ng as scheduler
import veritas.logging
from veritas.tools import tools


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
    parser_registry = subparsers.add_parser('registry', help='task registry')
    parser_scheduler = subparsers.add_parser('scheduler', help='task scheduler')
    parser_worker = subparsers.add_parser('worker', help='task worker')
    
    #
    # registry
    #
    parser_registry.add_argument('--import', type=str, dest="import_filename", required=False, help="import file to registry")

    #
    # scheduler
    #
    parser_scheduler.add_argument('--init', action='store_true', help='clean old values and initialize scheduler')
    parser_scheduler.add_argument('--show-jobs', action='store_true', help='show all jobs')
    parser_scheduler.add_argument('--schedule', action='store_true', help='start scheduling jobs')
    parser_scheduler.add_argument('--show-scheduled-jobs', action='store_true', help='show scheduled jobs')
    parser_scheduler.add_argument('--show-all-scheduled-jobs', action='store_true', help='show all scheduled jobs')
    parser_scheduler.add_argument('--run-now', type=int, required=False, help="run job now")
    parser_scheduler.add_argument('--no-daemon', action='store_true', help='exit after schedule jobs')

    #
    # worker
    # 
    parser_worker.add_argument('--profile', help='profile', default='default')
    parser_worker.add_argument('--username', help='username', default=None)
    parser_worker.add_argument('--password', help='password', default=None)

     # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    jobschleuder_config = tools.get_miniapp_config('jobschleuder', BASEDIR, args.config)
    if not jobschleuder_config:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=jobschleuder_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='jobschleuder',
        uuid=args.uuid)

    if args.command == 'registry':
        if args.import_filename:
            registry.import_file(jobschleuder_config.get('database',{}), args.import_filename)
    if args.command == 'scheduler':
        if args.init:
            scheduler.init(jobschleuder_config.get('database',{}))
        if args.show_jobs:
            scheduler.show_jobs(jobschleuder_config.get('database',{}))
        if args.show_scheduled_jobs:
            scheduler.show_scheduled_jobs(jobschleuder_config.get('database',{}))
        if args.show_all_scheduled_jobs:
            scheduler.show_all_scheduled_jobs(jobschleuder_config.get('database',{}))
        if args.run_now:
            scheduler.run_now(jobschleuder_config, args.run_now)
        if args.schedule:
            scheduler.schedule_jobs(jobschleuder_config, args.no_daemon)
    if args.command == "worker":
        worker.worker(jobschleuder_config)

if __name__ == "__main__":
    main()
