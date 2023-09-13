#!/usr/bin/env python

import argparse
import yaml
import logging
import os
from veritas.sot import sot as sot
from veritas.tools import tools
from dotenv import load_dotenv, dotenv_values
import run_playbook as pb
import import_update as imp_upd

# set default config file to your needs
default_config_file = "./conf/kobold.yaml"

def set_custom_field(args, sot, devicelist):
    for device in devicelist:
        hostname = device.get('hostname')
        address = device.get('host')
        cf_list = args.custom_field.split(',')
        updates = {}
        for custom_field in cf_list:
            cfs = custom_field.split('=')
            updates[cfs[0]] = cfs[1]
        logging.info(f'setting custom fields {updates} on {hostname}')
        sot.device(hostname).set_customfield(updates)

def set_tags(args, sot, devicelist):
    if args.interfaces:
        set_tags_on_interfaces(args, sot, devicelist)
    else:
        set_tags_on_devices(args, sot, devicelist)

def set_tags_on_interfaces(args, sot, devicelist):
    tags = args.set_tags.split(',')
    interfaces = args.interfaces.split(',')
    for device in devicelist:
        for interface in interfaces:
            if args.dry_run:
                print(f'setting tag {tags} on {device["hostname"]}/{interface}')
            else:
                logging.info(f'setting tag {tags} on {device["hostname"]}/{interface}')
                sot.device(device["hostname"]).interface(interface).add_tags(tags)
        
def set_tags_on_devices(args, sot, devicelist):
    tags = args.set_tags.split(',')
    for device in devicelist:
        if args.dry_run:
            print(f'setting tag {tags} on {device["hostname"]}')
        else:
            logging.info(f'setting tag {tags} on {device["hostname"]}')
            sot.device(device["hostname"]).add_tags(tags)

if __name__ == "__main__":

    devicelist = []

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="kobold config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="kobold loglevel")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # what devices 
    parser.add_argument('--devices', type=str, required=False, help="query to get list of devices")
    parser.add_argument('--interfaces', type=str, required=False, help="list of interfaces we are using")
    # what to do
    parser.add_argument('--playbook', type=str, required=False, help="run playbook")
    parser.add_argument('--job', type=str, required=False, help="run job(s) in playboook")
    parser.add_argument('--dry-run', action='store_true', help='just print what todo on what device or interface')
    parser.add_argument('--set-tags', type=str, required=False, help="set tags on device or interface")
    parser.add_argument('--custom-field', type=str, required=False, help="set value on custom field")
    # import or update device configgs
    parser.add_argument('--data', type=str, required=False, help='filename of data')
    parser.add_argument('--update', action='store_true', help='update device in SOT')
    parser.add_argument('--import', action='store_true', dest='import_data', help='import data from file')
    parser.add_argument('--value-mapping', type=str, required=False, help="filename to read value mapping")
    parser.add_argument('--force', action='store_true', help='update data even if no update were detected')

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

    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    with open(config_file) as f:
        kobold_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(kobold_config, ['kobold', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(kobold_config, ['kobold', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(kobold_config, ['kobold', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=kobold_config['sot']['token'], 
                  url=kobold_config['sot']['nautobot'])

    if args.playbook:
        # use playboook
        pb.run_playbook(args, sot, kobold_config)
    elif args.devices:
        devices = sot.select('hostname', 'primary_ip4', 'platform') \
                     .using('nb.devices') \
                     .normalize(False) \
                     .where(args.devices)

        if args.set_tags:
            set_tags(args, sot, devices)
        if args.custom_field:
            set_custom_field(args, sot, devices)
    elif args.import_data and not args.update:
        imp_upd.import_data(args, sot, kobold_config)
    elif args.import_data and args.update:
        imp_upd.update_data(args, sot, kobold_config)
