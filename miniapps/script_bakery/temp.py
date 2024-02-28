#!/usr/bin/env python

import sys
import napalm
import os
import logging

logger = logging.getLogger("napalm")
logger.setLevel(logging.DEBUG)

username = "lab"
password = "lab"
device = "192.168.0.1"
loglevel = "DEBUG"
config_directory = "./device_configs"

driver = napalm.get_network_driver('ios')
device = driver(
    hostname=device,
    username=username,
    password=password,
    optional_args={'inline_transfer': False}
)
device.open()

config_file = f'{config_directory}/{device.hostname}.config'
etx_char = chr(3)

# get running config
# running_config = device.get_config(retrieve='running')
# directory = os.path.dirname(config_file)
# if not os.path.exists(directory):
#     logger.debug(f'creating {directory}')
#     os.makedirs(directory)

# config = running_config['running']
# config = config.replace('^C', "\x03")

# with open(config_file, 'w') as f:
#     f.write(config)
logger.debug(f'loading {config_file}')
device.load_replace_candidate(filename=config_file)
device.commit_config()
