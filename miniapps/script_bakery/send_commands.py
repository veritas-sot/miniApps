#!/usr/bin/env python

import argparse
import os
import sys
import json
import yaml
import pandas as pd
from loguru import logger
from dotenv import load_dotenv, dotenv_values
from nornir_utils.plugins.functions import print_result
from nornir_inspect import nornir_inspect
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_get
from nornir_scrapli.tasks import send_configs
from nornir_netmiko.tasks import netmiko_save_config, netmiko_send_config

import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools

def send_commands_to_device(task: Task, commands, configure_device=False) -> Result:
    result = []
    # Manually create Netmiko connection
    net_connect = task.host.get_connection("netmiko", task.nornir.config)
    if configure_device:
        result.append({'cmd': 'config_mode', 'output': net_connect.config_mode()})
    for cmd in commands:
        result.append({'cmd': cmd, 'output': net_connect.send_command(cmd, expect_string=r"#")})
    if configure_device:
        result.append({'cmd': 'exit_config_mode', 'output': net_connect.exit_config_mode()})
    return Result(
        host=task.host,
        result=result
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
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    # command to send
    parser.add_argument('--command', type=str, required=False, help="single command to send")
    parser.add_argument('--playbook', type=str, required=False, help="playbook to use")
    parser.add_argument('--job', type=str, required=False, help="job to execute")
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
        app='send_commands',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=False)

    # load profiles
    profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')

    # get username and password either from profile
    username, password = tools.get_username_and_password(
            profile_config,
            args.profile,
            args.username,
            args.password)

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .add_data({'sot': ['cf_snmp_credentials']}) \
        .init_nornir()

    logger.debug(f'inventory: {nr.inventory.hosts}')

    if args.command:
        result = nr.run(
                name="send_command", task=send_commands_to_device, commands=[args.command]
        )
        print_result(result)
    elif args.playbook:
        logger.debug(f'reading playbook {args.playbook}')
        with open(args.playbook) as f:
            try:
                playbook = yaml.safe_load(f.read())
            except Exception as exc:
                logger.error(f'could not read or parse playbook {exc}')
                sys.exit()
        
        if args.job:
            jobs = playbook.get('playbook',{})
            table = []
            for job in jobs:
                name = job.get('job')
                if name == args.job:
                    logger.debug(f'executing job {args.job}')
                    configure = job.get('configure', False)
                    commands = job.get('commands')
                    results = nr.run(
                        name="send_command", 
                        task=send_commands_to_device, 
                        commands=commands,
                        configure_device=configure
                    )
                    hosts = results.keys()
                    for host in hosts:
                        commands = results[host][0].result
                        for command in commands:
                            key = command.get('cmd')
                            value = command.get('output')
                            table.append({'host': host, 'cmd': key, 'output': value})
            df = pd.DataFrame(table)
            print(df)

if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../script_bakery')
    import send_commands as sc

    sc.main(['--profile', 'default', 
             '--loglevel', 'debug',
             '--devices', 'name=lab.local'])


    """
    main()
