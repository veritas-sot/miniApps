#!/usr/bin/env python

import argparse
import os
import yaml
import sys
import json
import re
import time
import getpass
from loguru import logger
from dotenv import load_dotenv, dotenv_values
from nornir_inspect import nornir_inspect
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_get
from nornir_scrapli.tasks import send_configs
from nornir_netmiko.tasks import netmiko_save_config, netmiko_send_config

import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools


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
                logger.debug(f'user {existing_username} found in config')
            else:
                if args.dry_run:
                    removed_users.append('no ' + cmd)
        if len(removed_users) > 0 and not args.dry_run:
            logger.info(f'removing old User config of {hostname}')
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
        logger.debug(f'sending {new_config}')
        response = task.run(
            task=netmiko_remove_and_add_user, 
            new_users=new_config, 
            removed_users=removed_users
        )

    if (args.remove_old_config) and not args.dry_run:
        logger.debug(f'saving config on device {hostname}')
        # write config
        response = task.run(
            name="save_config",
            task=netmiko_save_config, 
        )

def main(args_list=None):

    devices = []
    username = None
    password = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

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
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug(f'reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug(f'no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('onboarding', BASEDIR, "salt.yaml")
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # read config
    local_config_file = tools.get_miniapp_config('script_bakery', BASEDIR, args.config)
    if not local_config_file:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='write_user_config',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False))

    # load profiles
    profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')

    # get username and password either from profile
    username, password = tools.get_username_and_password(
        profile_config,
        args.profile,
        args.username,
        args.password)

    # read new user config
    new_users = local_config_file.get('users')
    if not new_users:
        logger.error(f'found no users, giving up')
        sys.exit()

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .init_nornir()

    result = nr.run(
            name="write_user_config", task=write_user_config
    )

    #nornir_inspect(result)

if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../script_bakery')
    import write_user_config as wuc

    wuc.main(['--profile', 'default', 
              '--loglevel', 'debug',
              '--devices', 'name=lab.local'])

    """
    main()
