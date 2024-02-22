#!/usr/bin/env python

import argparse
import os
import json
from loguru import logger
from datetime import datetime
from dotenv import load_dotenv
from nornir_napalm.plugins.tasks import napalm_get
from nornir_utils.plugins.tasks.files import write_file

# veritas
import veritas.logging
import veritas.repo
import veritas.profile
from veritas.sot import sot as veritas_sot
from veritas.tools import tools


def backup_config(task, path, host_dirs, set_timestamp=False):

    dt = ""
    hostname = str(task.host)

    # Task 1. get configs from device
    logger.bind(extra=hostname).info('getting config')
    response = task.run(
        name="get_config",
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

    # Task 2. Write startup config to file
    logger.bind(extra=hostname).info(f'writing startup_config to {path}')
    task.run(
        name="write_startup_config",
        task=write_file,
        content=startup_config,
        filename=f'{prefix}.startup.cfg'
    )

    # Task 3. Write running config to file
    logger.bind(extra=hostname).info(f'writing running_config to {path}')
    task.run(
        name="write_running_config",
        task=write_file,
        content=running_config,
        filename=f'{prefix}.running.cfg'
    )

def main(args_list=None):

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
    parser.add_argument('--username', type=str, required=False, help="login username")
    parser.add_argument('--password', type=str, required=False, help="login password")
    parser.add_argument('--profile', type=str, required=False, help="profile to get login credentials")
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

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

    if args.backup_dir:
        backup_dir = args.backup_dir
        path_to_repo = backup_dir
    else:
        path_to_repo = local_config_file.get('git',{}).get('backup',{}).get('path',{})
        backup_dir = f'{path_to_repo}'

    logger.debug(f'backup_dir={backup_dir}')

    if not os.path.exists(backup_dir):
        logger.error(f'backup directory {backup_dir} does not exsists')
        return

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(profile=profile, result='result', parse=False) \
        .init_nornir()

    result = nr.run(
            name="backup_config", 
            task=backup_config, 
            path=backup_dir,
            host_dirs=local_config_file.get('backup',{}).get('individual_hostdir',True)
    )

    # analyze results and log to journal (if uuid is set)
    analysis = tools.analyze_nornir_result(result)
    for host, values in analysis.items():
        overall_failed = values.get('backup_config',{}).get('failed')
        result = {'app': 'backup_configs',
                  'details': {
                    'entity': host,
                    'message': json.dumps(values)}
        }
        logger.bind(extra=host, result=result).journal(f'backup of {host} failed: {overall_failed}')

    if args.no_git or not local_config_file.get('git',{}).get('backup',{}).get('enabled', True):
        result={'app': 'backup_configs',
                'details': {
                  'entity': 'git',
                  'message': 'git is deactivated'}
                }
        logger.bind(extra="git", result=result).journal('git is deactivated')
        return

    # now add all files to git staging
    name_of_repo = local_config_file.get('git',{}).get('backup',{}).get('repo',{})
    remote = local_config_file.get('git',{}).get('backup',{}).get('remote',{})
    logger.bind(extra="git").debug(f'add files to repo={name_of_repo} path={path_to_repo}')
    logger.bind(extra="git").debug(f'remote is set to {remote}')
    try:
        repo = veritas.repo.Repository(repo=name_of_repo, path=path_to_repo)
    except Exception as exc:
        logger.error(f'could not initialize git repo; got exception {exc}')
        result = {'app': 'backup_configs',
                  'details': {
                    'entity': 'git',
                    'message': 'could not initialize git repo'}
                 }
        logger.bind(extra="git", result=result).journal('could not initialize git repo')
        return

    # check that the origin matches
    if repo.remotes.origin.url != remote:
        logger.error('configured origin does not match')
        logger.error(f'{repo.remotes.origin.url} (configured)')
        logger.error(f'{remote} (configured in your YAML config)')
        return

    logger.debug(f'using origin url {remote}')
    has_changes = repo.has_changes()
    if not has_changes:
        result={'app': 'backup_configs',
                'details': {
                  'entity': 'git',
                  'message': 'no changes in git repo detected'}
                }
        logger.bind(extra="git", result=result).journal('no changes in git repo detected')
        return

    # get list of untracked files
    untracked = repo.get_untracked_files()
    result = {'app': 'backup_configs',
              'details': {
                'entity': 'git',
                'message': f'list of untracked files {untracked}'}
             }
    logger.bind(extra="git", result=result).journal(f'list of untracked files {untracked}')

    repo.add_all()
    now = datetime.now()
    dt = now.strftime("%Y_%m_%d_%H%M%S")
    logger.bind(extra="git").debug('commiting changes')
    commit = repo.commit(comment=f'config backup {dt}')
    logger.bind(extra="git").info('pushing changes')
    try:
        push = repo.push()[0]
        result = {'app': 'backup_configs',
                  'details': {
                    'entity': 'git',
                    'message': f'commit={commit}, push={push.summary}'}
                 }
        logger.bind(extra="git", result=result).journal(f'commmit: {commit} push: {push.summary}')
    except Exception as exc:
        logger.error(f'pushing configs to GIT failed; got exception {exc}')
        result = {'app': 'backup_configs',
                  'details': {
                    'entity': 'git',
                    'message': 'pushing configs to GIT failed'}
                 }
        logger.bind(extra="git", result=result).journal('pushing configs to GIT failed')


if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../script_bakery')
    import backup_configs as backup

    backup.main(['--profile', 'default', 
                 '--loglevel', 'debug',
                 '--devices', 'name=lab.local'])

    """
    main()
