#!/usr/bin/env python

import argparse
import yaml
import os
import urllib3
import json
import sys
import kobold
from dotenv import load_dotenv, dotenv_values
from loguru import logger

import veritas.logging
from veritas.sot import sot as sot
from veritas.tools import tools


# set default config file to your needs
default_config_file = "./conf/kobold.yaml"


if __name__ == "__main__":

    # init some vars
    listener = None

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="used config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # what to do
    parser.add_argument('--playbook', type=str, required=False, help="run playbook")
    parser.add_argument('--job', type=str, required=False, help="run job(s) in playboook")
    parser.add_argument('--dry-run', action='store_true', help='just print what todo on what device or interface')
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
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
    
    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    # read config
    kobold_config = tools.get_miniapp_config('kobold', BASEDIR, args.config)
    if not kobold_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=kobold_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='kobold',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=kobold_config['sot']['token'],
                  ssl_verify=kobold_config['sot'].get('ssl_verify', False),
                  url=kobold_config['sot']['nautobot'])

    if args.playbook:
        kobold = kobold.Kobold(sot, args.playbook)
        if args.port:
            kobold.set_tcp_port(args.port)
        if args.scrapli_loglevel:
            kobold.set_scrapli_loglevel(args.scrapli_loglevel)
        if args.profile:
            # load profiles
            profile_config = tools.get_miniapp_config('kobold', BASEDIR, 'profiles.yaml')
            # get username and password either from profile
            username, password = tools.get_username_and_password(
                    profile_config,
                    args.profile)
            kobold.set_profile(username=username, password=password)
        
        if args.job:
            for job in args.job.split(','):
                response = kobold.run(job)
    
    if listener:
        listener.stop()