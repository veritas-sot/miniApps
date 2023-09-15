#!/usr/bin/env python

import argparse
import logging
import os
import yaml
import json
import getpass
import sys
from datetime import datetime
from veritas.sot import sot as sot
from veritas.sot import repository
from veritas.tools import tools
from dotenv import load_dotenv, dotenv_values
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_utils.plugins.tasks.files import write_file
from nornir_utils.plugins.functions import print_result
from nornir_netmiko.tasks import netmiko_send_command


def backup_config(task, path, host_dirs, set_timestamp=False):

    dt = ""

    # Task 1. get configs
    response = task.run(
        name="config",
        task=napalm_get, getters=['config'], retrieve="all"
    )
    running_config = response[0].result.get('config',{}).get('running')
    startup_config = response[0].result.get('config',{}).get('startup')

    # get current date and time
    if set_timestamp:
        now = datetime.now()
        dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'

    # use individual host directories?
    if host_dirs:
        prefix = f'{path}/{task.host}/{task.host}{dt}'
        if not os.path.exists(f'{path}/{task.host}/'):
            os.makedirs(f'{path}/{task.host}/')
    else:
        prefix = f'{path}/{task.host}{dt}'

    # modify startup config
    # on some cisco switches the startup config begins with Using xx out of yy bytes
    if startup_config.startswith('Using '):
        startup_config = startup_config.split('\n',1)[1]

    # Task 2. Write startup config
    task.run(
        task=write_file,
        content=startup_config,
        filename=f'{prefix}.startup.cfg'
    )

    # Task 3. Write running config
    task.run(
        task=write_file,
        content=running_config,
        filename=f'{prefix}.running.cfg'
    )

if __name__ == "__main__":

    username = None
    password = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default="./config.yaml", required=False, help="set_snmp config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="configure loglevel")
    # what devices
    parser.add_argument('--devices', type=str, required=True, help="query to get list of devices")
    parser.add_argument('--backup-dir', type=str, required=False, help="backup dir")
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False)
    parser.add_argument('--password', type=str, required=False)
    parser.add_argument('--profile', type=str, required=False)
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    # Connect the path with the '.env' file name
    load_dotenv(os.path.join(BASEDIR, '.env'))

    # read config
    with open(args.config) as f:
        local_config_file = yaml.safe_load(f.read())

    # set loglevel before init our SOT!!!
    tools.set_loglevel(args, local_config_file)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=local_config_file['sot']['token'], url=local_config_file['sot']['nautobot'])

    # get username and password either from profile or by get username / getpass or args
    username, password = tools.get_username_and_password(args, sot, local_config_file)

    # check if backup directory exists
    if args.backup_dir:
        backup_dir = args.backup_dir
        path_to_repo = backup_dir
    else:
        path_to_repo = local_config_file.get('git',{}).get('backups',{}).get('path',{})
        subdir = local_config_file.get('git',{}).get('backups',{}).get('subdir','')
        backup_dir = f'{path_to_repo}/{subdir}'
    if not os.path.exists(backup_dir):
        logging.error(f'backup directory {backup_dir} does not exsists')
        sys.exit()
    
    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .init_nornir()

    result = nr.run(
            name="backup_config", 
            task=backup_config, 
            path=backup_dir,
            host_dirs=local_config_file.get('backup',{}).get('individual_hostdir',True)
    )

    # now add all files to git staging
    name_of_repo = local_config_file.get('git',{}).get('backups',{}).get('name',{})
    remote = local_config_file.get('git',{}).get('backups',{}).get('remote',{})
    repo = sot.repository(repo=name_of_repo, path=path_to_repo)

    # check that the origin matches
    if repo.remotes.origin.url != remote:
        logging.error(f'configured origin does not match')
        logging.error(f'{repo.remotes.origin.url} (configured)')
        logging.error(f'{remote} (should be)')
        sys.exit()

    logging.info(f'using origin url {remote}')
    has_changes = repo.has_changes()
    if not has_changes:
        logging.info(f'no changes in our git repo detected')
        sys.exit()
    untracked = repo.get_untracked_files()
    logging.info(f'list of untracked files')
    logging.info(untracked)

    repo.add_all()
    now = datetime.now()
    dt = now.strftime("%Y_%m_%d_%H%M%S")
    repo.commit(comment=f'updating config {dt}')
    repo.push()
