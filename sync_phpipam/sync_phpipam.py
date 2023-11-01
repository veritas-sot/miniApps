#!/usr/bin/env python

import argparse
import os
import logging
import json
import yaml
import phpipam
from veritas.sot import sot as sot
from veritas.tools import tools

default_config_file = "./config.yaml"
# Get the path to the directory this file is in
BASEDIR = os.path.abspath(os.path.dirname(__file__))


def sync_sot_to_phpipam(sot, phpipam, sync_config, cidr):
    logging.info("syncing %s from SOT to PHPIPAM" % cidr)

    sot_prefixe = sot.select(['prefix','description', 'tags']) \
                     .using('nb.prefixes') \
                     .normalize(True) \
                     .where(f'within_include={cidr}')

    section_by_id, section_by_name = phpipam.get_sections_from_phpipam()
    subnets = phpipam.get_prefixe_from_phpipam(cidr)

    for prefix in sot_prefixe:
        prfx = prefix.get('prefix')
        description = prefix.get('description','')
        logging.debug(f'looking for prefix {prfx}')
        if prfx not in subnets:
            logging.info(f'prefix {prfx} not found in PHPIPAM')
            section = "root"
            if 'tags' in prefix and prefix['tags'] != 'none' and prefix['tags']:
                for tag in prefix.get('tags', {}):
                    if 'section' in tag['name']:
                        section = tag['name'].split("section:")[1]
            phpipam.add_subnet_to_phpipam(prfx, section, description)
        else:
            should_be= "root"
            if 'tags' in prefix and prefix['tags'] != 'none' and prefix['tags']:
                for tag in prefix.get('tags', {}):
                    if 'section' in tag['name']:
                        should_be = tag['name'].split("section:")[1]
            is_in = subnets.get(prfx,{}).get('section_id')
            is_in_name = section_by_id.get(is_in,{}).get('name')
            if should_be != is_in_name:
                logging.info(f'prefix {prfx} should be in {should_be} but found in {is_in_name}')
                phpipam.add_subnet_to_phpipam(prfx, should_be, description, True)

def sync_phpipam_to_sot(cidr):
    logging.info("syncing %s from PHPIPAM to SOT" % cidr)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False, help="sync config file")
    parser.add_argument('--loglevel', type=str, required=False, help="loglevel")
    # what to do
    parser.add_argument('--sync-to-phpipam', action='store_true', help="sync sot to phpipam")
    parser.add_argument('--sync-to-sot', action='store_true', help="sync phpipam to sot")
    parser.add_argument('--cidr', type=str, required=False, default="0.0.0.0/0", help="sync all or only cidr")

    args = parser.parse_args()

    # read sync config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    with open(config_file) as f:
        sync_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(sync_config, ['check_mk', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(sync_config, ['check_mk', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(sync_config, ['check_mk', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=sync_config['sot']['token'], url=sync_config['sot']['nautobot'])
    phpipam_url = sync_config['phpipam']['backend']['phpipam_url']
    phpipam_appid = sync_config['phpipam']['backend']['phpipam_appid']
    phpipam_username = sync_config['phpipam']['backend']['phpipam_username']
    phpipam_password = sync_config['phpipam']['backend']['phpipam_password']

    pi = phpipam.Phpipam(url=phpipam_url, 
                         app_id=phpipam_appid, 
                         username=phpipam_username, 
                         password=phpipam_password,
                         ssl_verify=False)
    if args.sync_to_phpipam:
        sync_sot_to_phpipam(sot, pi, sync_config, args.cidr)
    if args.sync_to_sot:
        sync_phpipam_to_sot(sot, pi, sync_config, args.cidr)
