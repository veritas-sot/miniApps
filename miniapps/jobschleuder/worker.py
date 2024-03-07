#!/usr/bin/env python

import argparse
import urllib3
import os
import sys
import importlib
from loguru import logger
from dotenv import load_dotenv

# veritas
from veritas import sot
from veritas import tools
import veritas.logging


def import_plugins(onboarding_config):
    # import plugins
    plugins = onboarding_config.get('plugins')
    for plugin in plugins:
        package = plugins.get(plugin).get('plugin_dir')
        subpackage = plugins.get(plugin).get('plugin')
        logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')


def main(args_list=None):

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # devicelist is the list of devices we are processing
    devicelist = []

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--config', help='config file', default='config.yaml')
    parser.add_argument('--loglevel', help='loglevel', default='INFO')
    parser.add_argument('--loghandler', help='loghandler', default='console')
    parser.add_argument('--uuid', help='uuid', default='onboarding')
    parser.add_argument('--debug-veritas', help='debug veritas', action='store_true')
    parser.add_argument('--profile', help='profile', default='default')
    parser.add_argument('--username', help='username', default=None)
    parser.add_argument('--password', help='password', default=None)

    parser.add_argument('--jobs', help='filename of jobs to schedule', default='./jobs/jons.yaml', required=False)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('onboarding', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file and no salt.yaml file found')
            sys.exit()
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # read config
    jobschleuder_config = tools.get_miniapp_config('onboarding', BASEDIR, args.config)
    if not jobschleuder_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=jobschleuder_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='onboarding',
        uuid=args.uuid)

    # load profiles
    profile_config = tools.get_miniapp_config('onboarding', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=args.profile,
        username=args.username,
        password=args.password,
        ssh_key=None)

    # import onboarding plugins
    import_plugins(jobschleuder_config)

    # we need the SOT object to talk to it
    sot = sot.Sot(url=jobschleuder_config['sot']['nautobot'],
                  token=jobschleuder_config['sot']['token'],
                  ssl_verify=jobschleuder_config['sot'].get('ssl_verify', False),
                  debug=args.debug_veritas)

if __name__ == "__main__":
    main()