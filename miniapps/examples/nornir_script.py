#!/usr/bin/env python

import argparse
import os
import yaml
import sys
import json
from loguru import logger
from dotenv import load_dotenv, dotenv_values
from dotenv import load_dotenv, dotenv_values
from nornir_inspect import nornir_inspect
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_get
from nornir_scrapli.tasks import send_configs
from nornir_netmiko.tasks import netmiko_save_config, netmiko_send_config

import veritas.logging
from veritas.sot import sot as sot
from veritas.tools import tools

def my_nornir_task(task: Task) -> Result:

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

if __name__ == "__main__":

    devices = []
    username = None
    password = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default="./config.yaml", required=False, help="local config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
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

    # create logger environment
    #
    # adjust the name to your need
    #

    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='nornir_script',
        uuid=args.uuid)

    # set ttp loglevel
    logger.getLogger('ttp').setLevel(logger.CRITICAL)

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
        logger.error(f'found no users, giving up')
        sys.exit()

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .init_nornir()

    result = nr.run(
            name="my_nornir_task", task=my_nornir_task
    )

    nornir_inspect(result)