#!/usr/bin/env python

import argparse
import os
import yaml
import glob
import difflib
from loguru import logger
from veritas.sot import sot as sot
from veritas.tools import tools


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    # what devices
    parser.add_argument('--devices', type=str, required=True, help="query to get list of devices")
    parser.add_argument('--backup-dir', type=str, required=False, help="backup dir")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    local_config_file = tools.get_miniapp_config('script_bakery', BASEDIR, args.config)
    if not local_config_file:
        print('unable to read config')
        sys.exit()

    # create logger environment
    tools.create_logger_environment(local_config_file, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=local_config_file['sot']['token'], url=local_config_file['sot']['nautobot'])

    sot_devicelist = sot.select('hostname') \
                        .using('nb.devices') \
                        .where(args.devices)
    
    backup_dir = args.backup_dir if args.backup_dir else \
        local_config_file.get('backup',{}).get('backup_dir','./backups/')

    for device in sot_devicelist:
        hostname = device.get('hostname')
        directory = f'{backup_dir}/{hostname}'
        for running_filename in glob.glob(os.path.join(directory, "*running.cfg")):
            startup_filename = running_filename.replace('running', 'startup')
            logger.debug(f'comparing {running_filename} with {startup_filename}')

            #diff = difflib.HtmlDiff().make_table(startup_cfg, running_cfg)


            # with open(startup_filename, 'r') as sf:
            #     startup_cfg = sf.read()
            # with open(running_filename, 'r') as rf:
            #     running_cfg = rf.read()
            # diff = difflib.ndiff(running_cfg, startup_cfg)
            # delta = ''.join(x[2:] for x in diff if x.startswith('- '))
            # print (delta)

            with open(startup_filename, 'r') as sf, open(running_filename, 'r') as rf:
                diff = difflib.unified_diff(sf.readlines(), rf.readlines(), fromfile=startup_filename, tofile=running_filename)
                #diff = difflib.unified_diff(rf.readlines(), sf.readlines(), fromfile=running_filename, tofile=startup_filename)
            for line in diff:
                print(line.strip())