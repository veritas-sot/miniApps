#!/usr/bin/env python

import argparse
import os
import yaml
import sys
import json
import getpass
from loguru import logger
from veritas.sot import sot as sot
from veritas.tools import tools
from dotenv import load_dotenv, dotenv_values
from nornir_inspect import nornir_inspect
from nornir.core.task import Task, Result
from nornir_napalm.plugins.tasks import napalm_get
from nornir_scrapli.tasks import send_configs
from nornir_netmiko.tasks import netmiko_save_config, netmiko_send_config

_cache_snmp_credentials = None

def get_snmp_credentials(sot, config):

    global _cache_snmp_credentials

    if _cache_snmp_credentials is None:
        name_of_repo = config.get('credentials',{}).get('snmp',{}).get('repo')
        path_to_repo = config.get('credentials',{}).get('snmp',{}).get('path')
        subdir = config.get('credentials',{}).get('snmp',{}).get('subdir')
        filename = config.get('credentials',{}).get('snmp',{}).get('filename')

        # open repo
        repo = sot.repository(repo=name_of_repo, path=path_to_repo)
        # get SNMP credentials from SOT
        logger.debug(f'loading SNMP credentials from REPO {name_of_repo} FILE {subdir}/{filename}')
        snmp_credentials_text = repo.get(f'{subdir}/{filename}')
        _cache_snmp_credentials = yaml.safe_load(snmp_credentials_text).get('snmp',[])

def check_access_list(access_list, running_config):
    running_access_list = running_config[0].get('security',{}).get('access_list')
    if not running_access_list:
        return False

    # check if access list is in standard
    found_access_list = False
    if running_access_list.get('standard',{}).get(access_list):
        logger.debug(f'access list {found_access_list} found on device')
        found_access_list = True
    
    return found_access_list

def snmp_global_config(args, sot, host_properties, configparser, running_config, local_snmp_config_file, new_snmp_credentials):

    hostname = host_properties.get('hostname')
    primary_ip = host_properties.get('primary_ip4')

    running_snmp_config = running_config[0].get('management',{}).get('snmp')
    running_snmp_config_raw = configparser.get_section('snmp-server')

    global_snmp_config = local_snmp_config_file.get('snmp',{}).get('global_config')
    access_list = local_snmp_config_file.get('snmp',{}).get('defaults',{}).get('accesslist')

    # get SNMP version
    snmp_version = "v" + str(new_snmp_credentials.get('version','3'))

    configs = []
    for config in global_snmp_config:
        if config.get(snmp_version):
            if access_list:
                global_config_cmd = config.get(snmp_version)
                global_config_cmd = global_config_cmd + f' access {access_list}'
            global_config_cmd = global_config_cmd.replace('_security_group_',new_snmp_credentials.get('security_group'))
            configs.append(global_config_cmd)

    # check access list
    found_access_list = check_access_list(access_list, running_config)
    if not found_access_list and not args.force:
        logger.error(f'no access list {access_list} found on device; skipping')
        return []
    elif not found_access_list and args.force:
        logger.warning(f'no access list {access_list} found on device; check if config is correct')

    return configs
    
def snmp_user_config(args, sot, host_properties, running_config, local_snmp_config_file, new_snmp_credentials):

    hostname = host_properties.get('hostname')
    primary_ip = host_properties.get('primary_ip4')
    privacy_protocol = ''
    snmp_type = new_snmp_credentials.get('type','v3_auth_privacy')
    new_snmp_user_config = local_snmp_config_file.get('snmp',{}).get('users').get(snmp_type)
    if new_snmp_user_config is None:
        logger.error(f'unknown SNMP type {snmp_type}; please configure type')
        return []

    # we have to adjust the protocols
    if 'sha' in new_snmp_credentials.get('auth_protocol','').lower():
        auth_protocol = "sha"
    elif 'md5' in new_snmp_credentials.get('auth_protocol','').lower():
        auth_protocol = "md5"
    else:
        logger.error(f'unknown auth protocol ' + new_snmp_credentials.get('privacy_protocol'))
        return []

    if 'v3' == new_snmp_credentials.get('version'):
        if 'aes-128' in new_snmp_credentials.get('privacy_protocol','').lower():
            privacy_protocol = "aes 128"
        elif 'aes-192' in new_snmp_credentials.get('privacy_protocol','').lower():
            privacy_protocol = "aes 256"
        elif 'aes-256' in new_snmp_credentials.get('privacy_protocol','').lower():
            privacy_protocol = "aes 256"
        else:
            logger.error(f'unknown privacy protocol %s' % new_snmp_credentials.get('privacy_protocol'))
            return []        

    new_snmp_user_config = new_snmp_user_config.replace('_security_name_',new_snmp_credentials.get('security_name'))
    new_snmp_user_config = new_snmp_user_config.replace('_security_group_',new_snmp_credentials.get('security_group'))
    new_snmp_user_config = new_snmp_user_config.replace('_auth_protocol_', auth_protocol)
    new_snmp_user_config = new_snmp_user_config.replace('_auth_password_',new_snmp_credentials.get('auth_password'))
    new_snmp_user_config = new_snmp_user_config.replace('_privacy_protocol_', privacy_protocol)
    new_snmp_user_config = new_snmp_user_config.replace('_privacy_password_',new_snmp_credentials.get('privacy_password',''))

    # check if we have some access lists
    access_list = local_snmp_config_file.get('snmp',{}).get('defaults',{}).get('accesslist')
    if access_list:
        # check if access list is part of config
        new_snmp_user_config = new_snmp_user_config + f' access {access_list}'

    found_access_list = check_access_list(access_list, running_config)
    if not found_access_list and not args.force:
        logger.error(f'no access list {access_list} found on device; skipping')
        return []
    elif not found_access_list and args.force:
        logger.warning(f'no access list {access_list} found on device; check if config is correct')

    return [new_snmp_user_config]

def add_access_list(args, host_properties, local_snmp_config_file):

    hostname = host_properties.get('hostname')
    primary_ip = host_properties.get('primary_ip4')
    access_list_name = args.add_access_list
    access_list_type = local_snmp_config_file.get('snmp',{}).get('access-list',{}).get(access_list_name,{}).get('type','')
    access_list_config = local_snmp_config_file.get('snmp',{}).get('access-list',{}).get(access_list_name,{}).get('config','')

    configs = []
    if 'standard' == access_list_type:
        configs.append(f'ip access-list standard {access_list_name}')
        for key, value in access_list_config.items():
            configs.append(f'{key} {value}')

    return configs

def write_snmp_config(task: Task) -> Result:

    new_config = []
    hostname = task.host
    # overwrite identifier if user specified credentials
    if args.credentials:
        sot_snmp_credentials = args.credentials
    new_snmp_credentials = None

    sot_snmp_credentials = task.host.data.get('snmp_credentials')
    if not sot_snmp_credentials or sot_snmp_credentials == '':
        logger.error(f'host {hostname} has no snmp credentials configured')
        return

    for cred in _cache_snmp_credentials:
        if cred['id'] == sot_snmp_credentials:
            new_snmp_credentials = cred

    logger.debug(f'found SNMP credentials {new_snmp_credentials}')

    if new_snmp_credentials is None:
        logger.error(f'unknown SNMP credentials. Please configure SOT or user --credentials')
        return

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

    if args.remove_old_config:
        remove = []
        for cmd in configparser.get_section('snmp-server'):
            if not args.dry_run:
                remove.append('no ' + cmd)
        if len(remove) > 0 and not args.dry_run:
            logger.info(f'removing old SNMP config of {hostname}')
            logger.debug(f'sending {remove}')
            new_config = remove

    host_properties = {'hostname': hostname,
                       'primary_ip4': task.host.data.get('primary_ip4')
                      }

    if args.add_access_list:
        new_config = new_config + add_access_list(args, host_properties, local_snmp_config_file)

    if args.snmp_global_config:
        snmp_gc = snmp_global_config(args, 
                                     sot, 
                                     host_properties,
                                     configparser,
                                     running_config, 
                                     local_snmp_config_file, 
                                     new_snmp_credentials)
        if len(snmp_gc) == 0:
            # got no valid global config
            return None
        new_config = new_config + snmp_gc

    if args.snmp_user_config:
        snmp_uc = snmp_user_config(args, 
                                   sot, 
                                   host_properties, 
                                   running_config, 
                                   local_snmp_config_file, 
                                   new_snmp_credentials)
        if len(snmp_uc) == 0:
            # got no valid user config
            return None
        new_config = new_config + snmp_uc

    if (args.remove_old_config or args.snmp_global_config or args.snmp_user_config) and not args.dry_run:
        logger.debug(f'saving config on device {hostname}')

    if args.dry_run:
        print(f'sending the following commands to {hostname}:')
        for line in new_config:
            print(line)
    else:
        response = task.run(
            task=send_configs, 
            configs=new_config
        )
        logger.info(f'got response (new_config): {response[0]}')
        # write config
        response = task.run(
            name="save_config",
            task=netmiko_save_config, 
        )
        logger.info(f'got response (write): {response[0]}')

if __name__ == "__main__":

    devices = []
    username = None
    password = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default="./config.yaml", required=False, help="set_snmp config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # which config and what to do
    parser.add_argument('--credentials', type=str, required=False, help="don't use SOT, overwrite credentials")
    parser.add_argument('--dry-run', action='store_true', help="Make no changes, just print")
    parser.add_argument('--remove-old-config', action='store_true', help="Remove old SNMP config")
    parser.add_argument('--remove-old-users', action='store_true', help="Remove old SNMP users")
    parser.add_argument('--snmp-global-config', action='store_true', help="Add SNMP global config")
    parser.add_argument('--snmp-user-config', action='store_true', help="Add SNMP USER")
    parser.add_argument('--add-access-list', type=str, required=False, help="Add access list to config")
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
        local_snmp_config_file = yaml.safe_load(f.read())

    # create logger environment
    tools.create_logger_environment(local_snmp_config_file, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=local_snmp_config_file['sot']['token'], url=local_snmp_config_file['sot']['nautobot'])

    # get username and password either from profile or by get username / getpass or args
    username, password = tools.get_username_and_password(args, sot, local_snmp_config_file)

    # read SNMP credentials
    get_snmp_credentials(sot, local_snmp_config_file)

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(username=username, password=password, result='result', parse=False) \
        .add_data({'sot': ['cf_snmp_credentials']}) \
        .init_nornir()

    result = nr.run(
            name="write_snmp_config", task=write_snmp_config
    )

    
