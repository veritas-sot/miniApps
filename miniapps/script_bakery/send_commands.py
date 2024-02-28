#!/usr/bin/env python

import argparse
import os
import sys
import yaml
import pandas as pd
from loguru import logger
from dotenv import load_dotenv
#from nornir_utils.plugins.functions import print_result
from nornir.core.task import Task, Result
from nornir.core import Nornir

# veritas
import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools
import veritas.profile


def send_commands_to_device(task: Task, commands, configure_device=False) -> Result:
    result = []
    # Manually create Netmiko connection
    try:
        net_connect = task.host.get_connection("netmiko", task.nornir.config)
        if configure_device:
            result.append({'cmd': 'config_mode', 'output': net_connect.config_mode()})
        for cmd in commands:
            # check if we have to confirm the command
            if '| confirm' in cmd:
                cmd = cmd.replace('| confirm', '')
                result.append({'cmd': cmd, 'output': net_connect.send_command(cmd, expect_string=r"confirm")})
                result.append({'cmd': 'confirm', 'output': net_connect.send_command("y", expect_string=r"#")})
            else:
                result.append({'cmd': cmd, 'output': net_connect.send_command(cmd, expect_string=r"#")})
        if configure_device:
            result.append({'cmd': 'exit_config_mode', 'output': net_connect.exit_config_mode()})
    except Exception as exc:
        result.append({'cmd': 'error', 'output': str(exc)})

    return Result(
        host=task.host,
        result=result
    )

def playbook_to_run(nr:Nornir, playbook:str, job_id:str|None=None):
    logger.debug(f'reading playbook {playbook}')
    with open(playbook) as f:
        try:
            playbook = yaml.safe_load(f.read())
        except Exception as exc:
            logger.error(f'could not read or parse playbook {exc}')
            sys.exit()
    
    jobs = playbook.get('playbook',{})
    table = []
    for job in jobs:
        name = job.get('job')
        if name == job_id or not job_id:
            logger.debug(f'executing job {job}')
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

def main(args_list=None):

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
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

    #
    # add subparsers
    #

    # add subparsers
    subparsers = parser.add_subparsers(dest='command')
    parser_configure = subparsers.add_parser('configure', help='configure devices')
    parser_show = subparsers.add_parser('show', help='send command to devices')
    parser_playbook = subparsers.add_parser('playbook', help='playbook to run')

    # configure commands to send to devices
    parser_configure.add_argument('--cfg', type=str, required=False, help="single command to send")
    parser_configure.add_argument('--configs', type=str, required=False, help="run commands from file")

    # command to send
    parser_show.add_argument('--cmd', type=str, required=False, help="single configure command to send")
    parser_show.add_argument('--commands', type=str, required=False, help="run commands from file")

    # playbooks
    parser_playbook.add_argument('--playbook', type=str, required=True, help="playbook to use")
    parser_playbook.add_argument('--job', type=str, required=False, help="job to execute")

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    if not args.profile and not args.username:
        sys.exit('no profile or username given')

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    local_config_file = tools.get_miniapp_config('script_bakery', BASEDIR, args.config)
    if not local_config_file:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='backup_configs',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=False)

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('script_bakery', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file found and no salt.yaml file found')
            return
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # load profiles
    profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=args.profile,
        username=args.username,
        password=args.password,
        ssh_key=None)

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(profile=profile, result='result', parse=False) \
        .init_nornir()

    logger.debug(f'inventory: {nr.inventory.hosts}')

    if args.command == "show":
        configure = False
        commands = []
        if args.cmd:
            commands.append(args.cmd)
        if args.commands:
            # open file and read commands
            with open(args.commands, 'r') as f:
                commands = f.readlines()
    elif args.command == "configure":
        configure = True
        commands = []
        if args.cfg:
            commands.append(args.cfg)
        if args.configs:
            # open file and read commands
            with open(args.configs, 'r') as f:
                commands = f.readlines()
    elif args.playbook:
        playbook_to_run(nr, args.playbook, args.job)
        return

    results = nr.run(
            name="send_show_commands", 
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
            print(f'---- {host} ----')
            print(f'{key}\n{value}')
        

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
