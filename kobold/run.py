#!/usr/bin/env python

import argparse
import yaml
import os
import urllib3
import json
from dotenv import load_dotenv, dotenv_values
import kobold
from loguru import logger
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
    # Connect the path with the '.env' file name
    load_dotenv(os.path.join(BASEDIR, '.env'))
    
    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    # read config from file
    with open(config_file) as f:
        kobold_config = yaml.safe_load(f.read())
    
    # create logger environment
    tools.create_logger_environment(kobold_config, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=kobold_config['sot']['token'],
                  ssl_verify=kobold_config['sot'].get('ssl_verify', False),
                  url=kobold_config['sot']['nautobot'],
                  git=None)

    if args.playbook:
        kobold = kobold.Kobold(sot, args.playbook)
        if args.port:
            kobold.set_tcp_port(args.port)
        if args.scrapli_loglevel:
            kobold.set_scrapli_loglevel(args.scrapli_loglevel)
        if args.profile:
            username = kobold_config.get('profiles',{}).get(args.profile,{}).get('username')
            token = kobold_config.get('profiles',{}).get(args.profile,{}).get('password')
            kobold.set_profile(username=username, token=token, profile=True)
        
        if args.job:
            for job in args.job.split(','):
                response = kobold.run(job)
    
    if listener:
        listener.stop()