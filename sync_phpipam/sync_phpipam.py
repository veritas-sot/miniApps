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


def create_all_sections(sot, ipam, sync_config):
    """create all sections iin PHPIPAM"""

    # this is the config like cf_net~cf_net location and reflects the structure to add
    cfg_section = sync_config.get('sections').get('section','root')
    cfg_select = sync_config.get('sections').get('select','').split(',')
    select = ['prefix','description', 'tags', 'type']
    select += cfg_select

    # get all prefixes
    sot_prefixe = sot.select(select) \
                     .using('nb.prefixes') \
                     .normalize(False) \
                     .where(within_include='0.0.0.0/0')

    for prefix in sot_prefixe:
        cidr = prefix.get('prefix')
        cidr_type = prefix.get('type')
        if cidr == "0.0.0.0/0" and cidr_type == "CONTAINER":
            # we have to skip the 0.0.0.0/0 container, otherwise phpipam raises
            # an error 
            continue
        logging.debug(f'processing prefix {cidr}')
        create_sesctions(ipam, prefix, cfg_select, cfg_section, sync_config)

def create_all_locations(sot, ipam):
    locations_by_id, locations_by_name = ipam.get_locations()

    all_locations = sot.select('locations') \
                .using('nb.general') \
                .normalize(False) \
                .where()
    for location in all_locations.get('locations'):
        name = location.get('name')
        if name not in locations_by_name:
            logging.info(f'adding {location} to PHPIPAM')
            ipam.add_location({'name': name})

def create_all_customers(sot, ipam):
    customers_by_id, customers_by_name = ipam.get_customers()
    all_customers = sot.select('tenants') \
                .using('nb.general') \
                .normalize(False) \
                .where()
    # for customer in all_customers.get('customers'):
    #     name = customer.get('name')
    #     if name not in customers_by_name:
    #         logging.info(f'adding {customer} to PHPIPAM')
    #         ipam.add_customer({'name': name})

def get_section_name(prefix, cfg_section, sync_config):
    """return section name"""

    # the list of fields the user wants to replace
    cfg_select = sync_config.get('sections').get('select','').split(',')

    # first check if a tag named 'section' is configured
    if 'tags' in prefix and prefix['tags'] != 'none' and prefix['tags']:
        for tag in prefix.get('tags', {}):
            if 'section' in tag['name']:
                section = tag['name'].split("section:")[1]
    else:
        # use configured section instead of tag
        # we iterate through the SELECTED values and replace the configured
        # section with this values
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
    if len(section) == 0:
        section = sync_config.get('sections').get('default_section','root')
    logging.debug(f'prefix: {prefix.get("prefix")} section: "{section}"')
    return section

def create_sesctions(ipam, prefix, cfg_select, cfg_section, sync_config):
    """create section in PHPIPAM"""
    description = prefix.get('description','')
    permissions = sync_config.get('sections',{}).get('permissions','{"2":"3","3":"4","4":"3"}')

    list_of_sections = cfg_section.split('~')
    parent = ""
    for sct in list_of_sections:
        section = get_section_name(prefix, sct, sync_config)
        if section != parent:
            logging.info(f'adding section: "{section}" parent: "{parent}"')
            ipam.add_section(section, description, parent, permissions)
            parent = section

def get_subnet_config(prefix, sync_config):
    """return subnet config depending of the user config"""
    if prefix is None:
        return {}

    # get prefix path
    prefix_path = tools.get_prefix_path(sync_config.get('subnets'), prefix)
    subnet_config = {}
    # now loop through all prefixes
    for prfx in prefix_path:
        subnet_config.update(sync_config.get('subnets',{}).get(prfx))

    return subnet_config

def sync_sot_to_phpipam(sot, ipam, sync_config, where_cidr):
    logging.info("syncing %s from SOT to PHPIPAM" % where_cidr)

    cfg_select = sync_config.get('sections').get('select','').split(',')
    cfg_section = sync_config.get('sections').get('section','root')
    default_section = sync_config.get('sections').get('default_section','root')
    select = ['prefix','description', 'tags', 'type', 'location', '_custom_field_data']
    select += cfg_select

    sot_prefixe = sot.select(select) \
                     .using('nb.prefixes') \
                     .normalize(False) \
                     .where(f'within_include={where_cidr}')

    phpipam_subnets = ipam.get_prefixe(where_cidr)

    for prefix in sot_prefixe:
        cidr = prefix.get('prefix')
        cidr_type = prefix.get('type')
        logging.debug(f'processing prefix {cidr}')
        if cidr == "0.0.0.0/0" and cidr_type == "CONTAINER":
            # we have to skip the 0.0.0.0/0 container, otherwise phpipam raises
            # an error 
            continue
        description = prefix.get('description','')
        logging.debug(f'looking for prefix {cidr}')

        # get location from SOT
        if 'location' in prefix and prefix['location']:
            location = prefix.get('location',{}).get('name')
        else:
            location = None

        # get section string from config and split it
        # the user is able to configure sections and subsections
        # these (sub)sections are splitted by ~
        list_of_sections = cfg_section.split('~')
        l = len(list_of_sections) - 1 if len(list_of_sections) > 0 else 0
        # we need just the last (sub)section
        name_of_section = list_of_sections[l]
        # convert the configured section to the real name
        section = get_section_name(prefix, name_of_section, sync_config)
        if len(section) == 0:
            section = default_section
        logging.info(f'adding prefix {cidr} to section "{section}"')
        subnet_config = get_subnet_config(cidr, sync_config)
        # the user can set some phpipam specific settings
        # if 'phpipam' is in our custom_fields overwrite these values
        nb_phpipam_settinhgs = prefix.get('_custom_field_data',{}).get('phpipam',[])
        if isinstance(nb_phpipam_settinhgs, str):
            # if only one choice is selected the value is a string
            # but we need a list of strings instead
            nb_phpipam_settinhgs = [nb_phpipam_settinhgs]
        for setting in nb_phpipam_settinhgs:
            if len(setting) > 0:
                subnet_config[setting] = 1

        # set location if it is not None
        if location:
            subnet_config['location'] = location

        # add or update subnet
        ipam.add_subnet(cidr, section, subnet_config, description, cidr in phpipam_subnets)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False, help="sync config file")
    parser.add_argument('--loglevel', type=str, required=False, help="loglevel")
    parser.add_argument('--cidr', type=str, required=False, default="0.0.0.0/0", help="sync all or only specified cidr")
    parser.add_argument('--create-sections', action='store_true', help='create sections')
    parser.add_argument('--create-locations', action='store_true', help='create locations')
    parser.add_argument('--create-customers', action='store_true', help='create customers')

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

    ipam = phpipam.Phpipam(url=phpipam_url, 
                         app_id=phpipam_appid, 
                         username=phpipam_username, 
                         password=phpipam_password,
                         ssl_verify=False)

    if args.create_sections:
        create_all_sections(sot, ipam, sync_config)
    if args.create_locations:
        create_all_locations(sot, ipam)
    if args.create_customers:
        create_all_customers(sot, ipam)
    # add subnets to PHPIPAM
    sync_sot_to_phpipam(sot, ipam, sync_config, args.cidr)
