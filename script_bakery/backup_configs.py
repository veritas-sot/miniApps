#!/usr/bin/env python

import argparse
import logging
import os
import yaml
import json
from datetime import datetime
from veritas.sot import sot as sot
from veritas.tools import tools
from dotenv import load_dotenv, dotenv_values
from nornir import InitNornir
from nornir_napalm.plugins.tasks import napalm_get
from nornir_utils.plugins.tasks.files import write_file
from nornir_utils.plugins.functions import print_result
from nornir_netmiko.tasks import netmiko_send_command


def backup_config(task, path, host_dirs):
    # Task 1. get configs
    response = task.run(
        name="config",
        task=napalm_get, getters=['config'], retrieve="all"
    )
    running_config = response[0].result.get('config',{}).get('running')
    startup_config = response[0].result.get('config',{}).get('startup')

    # get current date and time
    now = datetime.now()
    dt = now.strftime("%Y_%m_%d_%H%M%S")

    # use individual host directories?
    if host_dirs:
        prefix = f'{path}/{task.host}/{task.host}_{dt}'
        if not os.path.exists(f'{path}/{task.host}/'):
            os.makedirs(f'{path}/{task.host}/')
    else:
        prefix = f'{path}/{task.host}_{dt}'

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

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(local_config_file, ['general', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(local_config_file, ['general', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(local_config_file, ['general', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=local_config_file['sot']['token'], url=local_config_file['sot']['nautobot'])

    # get username and password from profile if user configured args.profile
    if args.profile is not None:
        username = local_config_file.get('profiles',{}).get(args.profile,{}).get('username')
        token = local_config_file.get('profiles',{}).get(args.profile,{}).get('password')
        auth = sot.auth(encryption_key=os.getenv('ENCRYPTIONKEY'), 
                        salt=os.getenv('SALT'), 
                        iterations=int(os.getenv('ITERATIONS')))
        password = auth.decrypt(token)

    # overwrite username and password if configured by user
    username = args.username if args.username else username
    password = args.password if args.password else password

    username = input("Username (%s): " % getpass.getuser()) if not username else username
    password = getpass.getpass(prompt="Enter password for %s: " % username) if not password else password

    # check if backup directory exists
    backup_dir = args.backup_dir if args.backup_dir else \
        local_config_file.get('backup',{}).get('backup_dir','./backups/')
    if not backup_dir.startswith('/'):
        backup_dir = f'{BASEDIR}/{backup_dir}'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
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
