#!/usr/bin/env python

import sys
import argparse

# veritas
from veritas.journal import journal
from veritas.tools import tools
from veritas.logging import minimal_logger

# set import path to our script_bakery
sys.path.append('../sync_cmk')
# and now import the backup script
import sync_cmk as sync_cmk


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=str, default="sync_cmk", required=False, help="the key to get the uuid")
    parser.add_argument('--profile', type=str, required=True, help="profile to get login credentials")
    parser.add_argument('--loglevel', type=str, required=False, default="INFO", help="used loglevel")

    args = parser.parse_args()

    minimal_logger(args.loglevel)

    @journal.activity(journal=args.id, 
                      app='sync_cmk', 
                      description='synchronize checkmk')
    def sync(*args, **kwargs):
        properties = tools.convert_arguments_to_properties(args, kwargs)
        args = properties.get('args')
        sync_cmk.main(['--loglevel', args.loglevel,
                       '--update-hosts','',
                       '--uuid', properties['uuid']])

    sync(args=args)

if __name__ == "__main__":
    main()

