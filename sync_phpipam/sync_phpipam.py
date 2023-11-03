#!/usr/bin/env python

import argparse
import os
import logging
import json
import yaml
import phpipam
import sys
from veritas.sot import sot as sot
from veritas.tools import tools

default_config_file = "./config.yaml"
# Get the path to the directory this file is in
BASEDIR = os.path.abspath(os.path.dirname(__file__))


def get_section(prefix, cfg_select, cfg_section):
    # first check if a tag named 'section' is configured
    # print(f'cfg_select: {cfg_select} cfg_section: {cfg_section}')
    if 'tags' in prefix and prefix['tags'] != 'none' and prefix['tags']:
        for tag in prefix.get('tags', {}):
            if 'section' in tag['name']:
                section = tag['name'].split("section:")[1]
    else:
        # use configured section instead of tag
        section = cfg_section
        for slct in cfg_select:
            # logging.debug(f'- prefix: {prefix.get("prefix")} slct: {slct} cfg_section: {cfg_section}')
            if slct.startswith('cf_'):
                v = prefix.get('_custom_field_data',{}).get(slct.replace('cf_',''),'')
            else:
                v = prefix.get(slct)
            if not v:
                v = ''
            if isinstance(v, dict):
                if 'name' in v:
                    v = v.get('name')
            # logging.debug(f'prefix: {prefix.get("prefix")} slct: {slct} v: {v}')
            section = section.replace(slct, v)

    section = section.strip()
    # logging.debug(f'prefix: {prefix.get("prefix")} section: "{section}"')
    return section

def sync_sot_to_phpipam(sot, phpipam, sync_config, cidr):
    logging.info("syncing %s from SOT to PHPIPAM" % cidr)

    cfg_select = sync_config.get('select','').split(',')
    cfg_section = sync_config.get('section','root')
    default_section = sync_config.get('default_section','root')
    select = ['prefix','description', 'tags', 'type']
    select += cfg_select

    sot_prefixe = sot.select(select) \
                     .using('nb.prefixes') \
                     .normalize(False) \
                     .where(f'within_include={cidr}')

    section_by_id, section_by_name = phpipam.get_sections_from_phpipam()
    phpipam_subnets = phpipam.get_prefixe_from_phpipam(cidr)

    for prefix in sot_prefixe:
        cidr = prefix.get('prefix')
        cidr_type = prefix.get('type')
        if cidr == "0.0.0.0/0" and cidr_type == "CONTAINER":
            # we have to skip the 0.0.0.0/0 container, otherwise phpipam raises
            # an error 
            continue
        description = prefix.get('description','')
        logging.debug(f'looking for prefix {cidr}')
        if cidr not in phpipam_subnets:
            logging.info(f'prefix {cidr} not found in PHPIPAM')
            list_of_sections = cfg_section.split('~')
            parent = ""
            for sct in list_of_sections:
                # add sections to phpipam
                section = get_section(prefix, cfg_select, sct)
                if section != parent:
                    logging.debug(f'add section: "{section}" parent: "{parent}"')
                    phpipam.add_section_to_phpipam(section, section, parent)
                    parent = section
            logging.info(f'adding prefix {cidr} to section "{section}"')
            phpipam.add_subnet_to_phpipam(cidr, section, description)
        else:
            logging.info(f'prefix {cidr} found in phpipam')
            # is_in = phpipam_subnets.get(cidr,{}).get('section_id')
            # is_in_name = section_by_id.get(is_in,{}).get('name')
            # should_be = get_section(prefix, cfg_select, cfg_section)
            # if should_be != is_in_name:
            #     logging.info(f'prefix {cidr} should be in {should_be} but found in {is_in_name}')
            #     phpipam.add_subnet_to_phpipam(cidr, should_be, description, True)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False, help="sync config file")
    parser.add_argument('--loglevel', type=str, required=False, help="loglevel")
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

    sync_sot_to_phpipam(sot, pi, sync_config, args.cidr)
