#!/usr/bin/env python

import argparse
import logging
import os
import yaml
import sys
import json
import re
import time
import getpass
from veritas.sot import sot as sot
from veritas.tools import tools
from dotenv import load_dotenv, dotenv_values
from nornir_inspect import nornir_inspect
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_get
from nornir_scrapli.tasks import send_configs
from nornir_netmiko.tasks import netmiko_save_config, netmiko_send_config


def netmiko_remove_and_add_user(task, new_users, removed_users):

    # Manually create Netmiko connection
    net_connect = task.host.get_connection("netmiko", task.nornir.config)
    output = net_connect.config_mode()
    for cmd in new_users:
        output += net_connect.send_command(cmd, expect_string=r"#")
    for cmd in removed_users:
        output += net_connect.send_command(cmd, expect_string=r"confirm")
        output += net_connect.send_command("y", expect_string=r"#")
    output += net_connect.exit_config_mode()
    return output

def write_user_config(task: Task) -> Result:

    hostname = task.host
    # first of all: get current running config
    response = task.run(
        name="config",
        task=napalm_get, getters=['config'], retrieve="running"
    )
    device_config = response[0].result.get('config',{}).get('running')
    
    # now parse the config
    configparser = sot.configparser(config=device_config, platform='ios')
    if configparser.could_not_parse():
        return None

    running_config_raw = configparser.get(output_format='json')
    running_config = json.loads(running_config_raw)
    new_config = []
    removed_users = []

    # do we have to remove the old config
    if args.remove_old_config:
        for cmd in configparser.get_section('username '):
            # we are removing all users BUT those we have to add
            match = re.search('username (\w+) .*', cmd)
            if match:
                existing_username = match.group(1)
            if any(d['username'] ==  existing_username for d in new_users):
                logging.debug(f'user {existing_username} found in config')
            else:
                if args.dry_run:
                    removed_users.append('no ' + cmd)
        if len(removed_users) > 0 and not args.dry_run:
            logging.info(f'removing old User config of {hostname}')
        elif args.dry_run:
            print(f'removing old user config')
            print(f'sending {removed_users}')

    # now add new users
    for user in new_users:
        new_config.append(f'username {user["username"]} privilege {user["privilege"]} secret {user["secret"]}')

    if args.dry_run:
        print(f'sending new user config to {hostname}')
        for line in new_config:
            print(line)
    elif len(new_config) > 0 and not args.dry_run:
        logging.debug(f'sending {new_config}')
        response = task.run(
            task=netmiko_remove_and_add_user, 
            new_users=new_config, 
            removed_users=removed_users
        )

    if (args.remove_old_config) and not args.dry_run:
        logging.debug(f'saving config on device {hostname}')
        # write config
        response = task.run(
            name="save_config",
            task=netmiko_save_config, 
        )

if __name__ == "__main__":

    devices = []
    username = None
    password = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default="./config.yaml", required=False, help="local config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="configure loglevel")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # which config and what to do
    parser.add_argument('--dry-run', action='store_true', help="Make no changes, just print")
    parser.add_argument('--remove-old-config', action='store_true', help="Remove old User config")
    parser.add_argument('--force', action='store_true', help="Add config even if problem may occure")
    # what devices
    parser.add_argument('--devices', type=str, required=True, help="query to get list of devices")
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

    # set scrapli loglevel
    logging.getLogger('scrapli').setLevel(tools.get_loglevel(args.scrapli_loglevel))
    logging.getLogger('scrapli').propagate = True

    # set ttp loglevel
    logging.getLogger('ttp').setLevel(logging.CRITICAL)

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

    # read new user config
    new_users = local_config_file.get('users')
    if not new_users:
        logging.error(f'found no users, giving up')
        sys.exit()

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .init_nornir()

    result = nr.run(
            name="write_user_config", task=write_user_config
    )

    #nornir_inspect(result)