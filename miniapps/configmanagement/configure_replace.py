#!/usr/bin/env python

import argparse
import os
from loguru import logger
from dotenv import load_dotenv

# veritas
import veritas.logging
import veritas.profile
from veritas.tools import tools
from veritas.devicemanagement import napalm as dm


def main():

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False)
    parser.add_argument('--password', type=str, required=False)
    parser.add_argument('--profile', type=str, required=False)
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    parser.add_argument('--device', type=str, required=True, help="IP or name of device")

    subparsers = parser.add_subparsers(dest='command')
    parser_get = subparsers.add_parser('get', help='get running config')
    parser_replace = subparsers.add_parser('replace', help='replace config')

    parser_get.add_argument('--directory', type=str, default="./device_configs", required=False, help="filename of config")
    parser_get.add_argument('--filename', type=str, required=False, help="filename of config")

    parser_replace.add_argument('--directory', type=str, default="./device_configs", required=False, help="filename of config")
    parser_replace.add_argument('--filename', type=str, required=False, help="filename of config")
    parser_replace.add_argument('--timeout', type=int, default=60, required=False, help="filename of config")

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

    # get connection to device
    conn = dm.Devicemanagement(
        ip=args.device,
        platform="ios",
        manufacturer="cisco",
        username=profile.username,
        password=profile.password,
        port=args.port)

    logger.debug(f'opening connection to {args.device}')
    conn.open(
        timeout=args.timeout,
        optional_args={'inline_transfer': False}
    )
    config_file = f'{args.directory}/{args.device}.config'

    if args.command == "get":
        # get running config
        running_config = conn.get_config(configtype='running')
        running_config = running_config.replace('^C', "\x03")
        directory = os.path.dirname(config_file)
        if not os.path.exists(directory):
            os.makedirs(directory)
        logger.debug(f'writing {config_file}')
        with open(config_file, 'w') as f:
            f.write(running_config)
    elif args.command == "replace":
        logger.info(f'uploading {config_file}')
        conn.load_config(filename=config_file)
        logger.info(f'committing {config_file}')
        conn.commit_config()

if __name__ == "__main__":
    main()