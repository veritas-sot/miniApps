#!/usr/bin/env python

import sys
import argparse

# veritas
from veritas.journal import journal
from veritas.tools import tools
from veritas.logging import minimal_logger
from veritas.cron import schedule

# set import path to our script_bakery
sys.path.append('../script_bakery')
# and now import the backup script
import compare_configs as compare

@schedule('every(1).days.at("22:06")', args={'args_list': ['--profile','default','--id','daily_compare']})
def main(args_list=None):

    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=str, default="daily_jobs", required=False, help="the key to get the uuid")
    parser.add_argument('--profile', type=str, required=True, help="profile to get login credentials")
    parser.add_argument('--loglevel', type=str, required=False, default="INFO", help="used loglevel")

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    minimal_logger(args.loglevel)

    @journal.activity(journal=args.id, 
                      app='compare_configs', 
                      description='comparing running and startup configs')
    def compare_config(*args, **kwargs):
        properties = tools.convert_arguments_to_properties(args, kwargs)
        args = properties.get('args')
        compare.main(['--profile', args.profile, 
                      '--loglevel', args.loglevel,
                      '--devices', 'name=lab.local',
                      '--output', 'log',
                      '--uuid', properties['uuid']])

    compare_config(args=args)

if __name__ == "__main__":
    main(['--profile','default'])

