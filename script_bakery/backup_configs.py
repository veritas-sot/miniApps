#!/usr/bin/env python

import argparse
import os
import yaml
import json
import getpass
import sys
from loguru import logger
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
    logger.bind(extra=task.host).info('getting config')
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
    logger.bind(extra=task.host).info(f'writing startup_config to {path}')
    task.run(
        task=write_file,
        content=startup_config,
        filename=f'{prefix}.startup.cfg'
    )

    # Task 3. Write running config
    logger.bind(extra=task.host).info(f'writing running_config to {path}')
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
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    # what devices
    parser.add_argument('--devices', type=str, required=True, help="query to get list of devices")
    parser.add_argument('--backup-dir', type=str, required=False, help="backup dir")
    parser.add_argument('--no-git', action='store_true', help='deactivate git')
    
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
    tools.create_logger_environment(local_config_file, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=local_config_file['sot']['token'], url=local_config_file['sot']['nautobot'])

    # load profiles
    profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')

    # get username and password either from profile or by get username / getpass or args
    username, password = tools.get_username_and_password(args, sot, profile_config)

    # check if backup directory exists
    if args.backup_dir:
        backup_dir = args.backup_dir
        path_to_repo = backup_dir
    else:
        path_to_repo = local_config_file.get('git',{}).get('backups',{}).get('path',{})
        subdir = local_config_file.get('git',{}).get('backups',{}).get('subdir','')
        backup_dir = f'{path_to_repo}/{subdir}'
    if not os.path.exists(backup_dir):
        logger.error(f'backup directory {backup_dir} does not exsists')
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

    if args.no_git or not local_config_file.get('git',{}).get('backups',{}).get('active', True):
        logger.bind(extra="git").info(f'git is deactivated....')
        sys.exit()

    # now add all files to git staging
    name_of_repo = local_config_file.get('git',{}).get('backups',{}).get('repo',{})
    remote = local_config_file.get('git',{}).get('backups',{}).get('remote',{})
    logger.bind(extra="git").debug(f'add files to repo {name_of_repo} / {path_to_repo}')
    logger.bind(extra="git").debug(f'remote is set to {remote}')
    repo = sot.repository(repo=name_of_repo, path=path_to_repo)

    # check that the origin matches
    if repo.remotes.origin.url != remote:
        logger.error(f'configured origin does not match')
        logger.error(f'{repo.remotes.origin.url} (configured)')
        logger.error(f'{remote} (should be)')
        sys.exit()

    logger.debug(f'using origin url {remote}')
    has_changes = repo.has_changes()
    if not has_changes:
        logger.bind(extra="git").info(f'no changes in our git repo detected')
        sys.exit()

    # get list of untracked files
    untracked = repo.get_untracked_files()
    logger.bind(extra="git").debug(f'list of untracked files')
    logger.bind(extra="git").debug(untracked)

    repo.add_all()
    now = datetime.now()
    dt = now.strftime("%Y_%m_%d_%H%M%S")
    logger.bind(extra="git").debug(f'commiting changes')
    repo.commit(comment=f'config backup {dt}')
    logger.bind(extra="git").info(f'pushing changes')
    repo.push()
