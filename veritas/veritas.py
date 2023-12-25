#!/usr/bin/env python

import argparse
import os
import yaml
import shutil
import json
from loguru import logger


# set default config file to your needs
default_config_file = "./config.yaml"

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--write-config', action='store_true', help='write config')
    parser.add_argument('--write-dotenv', action='store_true', help='write .env files')
    parser.add_argument('--backup', action='store_true', help='backup current config')
    parser.add_argument('--cleanup', action='store_true', help='remove cofnig and .env files')
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="veritas config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used logging handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    
    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    with open(config_file) as f:
        veritas_config = yaml.safe_load(f.read())

    # create logger environment
    tools.create_logger_environment(veritas_config, args.loglevel, args.loghandler)

    # set default values
    nautobot_url = veritas_config.get('nautobot').get('url')
    nautobot_token = veritas_config.get('nautobot').get('token')

    if args.cleanup:
        for miniapp, configfile in veritas_config.get('configs').items():
            dstfile = configfile.replace('.example','')
            logger.info(f'removing {dstfile}')
            os.remove(dstfile)
        for dotenv, configfile in veritas_config.get('dotenv').items():
            dstfile = configfile.replace('.example','')
            logger.info(f'removing {dstfile}')
            os.remove(dstfile)

    for miniapp, configfile in veritas_config.get('configs').items():
        if args.backup:
            logger.info(f'backup {miniapp}')
            # check if target directory exists
            path = f"./backup/{miniapp}"
            srcfile = configfile.replace('.example','')
            dstfile = "%s/%s" % (path, configfile.split('/')[-1].replace('.example',''))
            if not os.path.exists(path):
                logger.info(f'creating missing directory {path}')
                os.makedirs(path)
            logger.info(f'backup {srcfile} {dstfile}')
            if os.path.exists(srcfile):
                shutil.copyfile(srcfile, dstfile)
            else:
                logger.error(f'no config {srcfile} found')

        if args.write_config:
            dstfile = configfile.replace('.example','')
            with open(configfile) as f:
                config = f.read()
                config = config.replace('__TOKEN__',nautobot_token)
                config = config.replace('__NAUTOBOT__',nautobot_url)
                # make a copy of our default values
                values = dict(veritas_config.get('defaults'))
                if miniapp in veritas_config:
                    logger.debug(f'found {miniapp} in veritas_config')
                    miniapp_cfg = veritas_config.get(miniapp)
                    # overwrite default values with miniapps values
                    for key, value in miniapp_cfg.items():
                        values[key] = value
                # now find and replace values
                for key, value in values.items():
                    logger.debug(f'key {key} value {value}')
                    src = f"__{key.upper()}__"
                    config = config.replace(src, str(value))
                for account in veritas_config.get('accounts'):
                    username = account.get('username')
                    password = account.get('password')
                    config = config.replace('__USERNAME__', username)
                    config = config.replace('__PASSWORD__', password)
            logger.info(f'writing config of {miniapp} to {dstfile}')
            with open(dstfile, "w") as f:
                f.write(config)
    
    for dotenv, configfile in veritas_config.get('dotenv').items():
        if args.write_dotenv:
            dstfile = configfile.replace('.example','')
            with open(configfile) as f:
                config = f.read()
                config = config.replace('__ENCRYPTIONKEY__', veritas_config.get('defaults').get('encryptionkey'))
                config = config.replace('__SALT__', veritas_config.get('defaults').get('salt'))
                config = config.replace('__ITERATIONS__', str(veritas_config.get('defaults').get('iterations')))
                logger.info(f'writing config of {dotenv} to {dstfile}')
                with open(dstfile, "w") as f:
                    f.write(config)
