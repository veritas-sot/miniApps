#!/usr/bin/env python

import argparse
import os
import json
import yaml
import phpipam
import sys
import urllib3
from loguru import logger

import veritas.logging
from veritas.sot import sot as sot
from veritas.tools import tools


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
                     .where(within_include='0.0.0.0/0')

    for prefix in sot_prefixe:
        cidr = prefix.get('prefix')
        cidr_type = prefix.get('type')
        if cidr == "0.0.0.0/0" and cidr_type == "CONTAINER":
            # we have to skip the 0.0.0.0/0 container, otherwise phpipam raises
            # an error 
            continue
        logger.debug(f'processing prefix {cidr}')
        create_section(ipam, prefix, cfg_select, cfg_section, sync_config)

def create_all_locations(sot, ipam):
    locations_by_id, locations_by_name = ipam.get_locations()

    all_locations = sot.select('locations') \
                .using('nb.general') \
                .where()
    for location in all_locations.get('locations'):
        name = location.get('name')
        if name not in locations_by_name:
            logger.info(f'adding {location} to PHPIPAM')
            ipam.add_location({'name': name})

def create_all_customers(sot, ipam):
    customers_by_id, customers_by_name = ipam.get_customers()
    all_customers = sot.select('tenants') \
                       .using('nb.general') \
                       .where()
    for customer in all_customers.get('customers'):
        name = customer.get('name')
        if name not in customers_by_name:
            logger.info(f'adding {customer} to PHPIPAM')
            ipam.add_customer({'name': name})

def create_section(ipam, prefix, cfg_select, cfg_section, sync_config):
    """create section in PHPIPAM"""
    description = prefix.get('description','')
    permissions = sync_config.get('sections',{}).get('permissions','{"2":"3","3":"4","4":"3"}')

    list_of_sections = cfg_section.split('~')
    parent = ""
    for sct in list_of_sections:
        section = get_section_name(prefix, sct, sync_config)
        if section != parent:
            logger.info(f'adding section: "{section}" parent: "{parent}"')
            ipam.add_section(section, description, parent, permissions)
            parent = section
    
    # the folder is added in the last section
    folder = get_folder_name(prefix, sync_config)
    if folder:
        ipam.add_folder(folder, section)

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
            # logger.debug(f'- prefix: {prefix.get("prefix")} slct: {slct} cfg_section: {cfg_section}')
            if slct.startswith('cf_'):
                v = prefix.get('custom_field_data', 
                               prefix.get('_custom_field_data',{})).get(slct.replace('cf_',''),'')
            else:
                v = prefix.get(slct)
            if not v:
                v = ''
            if isinstance(v, dict):
                if 'name' in v:
                    v = v.get('name')
            # logger.debug(f'prefix: {prefix.get("prefix")} slct: {slct} v: {v}')
            section = section.replace(slct, v)

    section = section.strip()
    if len(section) == 0:
        section = sync_config.get('sections').get('default_section','root')
    logger.debug(f'prefix: {prefix.get("prefix")} section: "{section}"')
    return section

def get_folder_name(prefix, sync_config):

    # the list of fields the user wants to replace
    cfg_select = sync_config.get('sections').get('select','').split(',')

    folder = sync_config.get('sections').get('folders')
    if not folder or folder == 'False':
        return None
    for fldr in cfg_select:
        # logger.debug(f'- prefix: {prefix.get("prefix")} fldr: {fldr} cfg_section: {cfg_section}')
        if fldr.startswith('cf_'):
            v = prefix.get('custom_field_data',
                       prefix.get('_custom_field_data',{})).get(fldr.replace('cf_',''),'')
        else:
            v = prefix.get(fldr)
        if not v:
            v = ''
        if isinstance(v, dict):
            if 'name' in v:
                v = v.get('name')
        # logger.debug(f'prefix: {prefix.get("prefix")} fldr: {fldr} v: {v}')
        folder = folder.replace(fldr, v)

    folder = folder.strip()
    return folder

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

def add_prefixes_to_phpipam(sot, ipam, sync_config, where_cidr, containers):
    logger.info("syncing %s from SOT to PHPIPAM" % where_cidr)

    cfg_select = sync_config.get('sections').get('select','').split(',')
    cfg_section = sync_config.get('sections').get('section','root')
    default_section = sync_config.get('sections').get('default_section','root')
    select = ['prefix','description', 'tags', 'type', 'location', '_custom_field_data']
    select += cfg_select

    sot_prefixe = sot.select(select) \
                     .using('nb.prefixes') \
                     .where(f'within_include={where_cidr}')

    phpipam_subnets = ipam.get_prefixe(where_cidr)

    for prefix in sot_prefixe:
        cidr = prefix.get('prefix')
        cidr_type = prefix.get('type')
        if cidr == "0.0.0.0/0" and cidr_type == "CONTAINER":
            # we have to skip the 0.0.0.0/0 container, otherwise phpipam raises
            # an error 
            continue
        if containers and cidr_type != "CONTAINER":
            continue

        logger.debug(f'processing prefix {cidr} type: {cidr_type}')
        description = prefix.get('description','')

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
        logger.info(f'adding prefix {cidr} to section "{section}"')
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
        folder = get_folder_name(prefix, sync_config)
        ipam.add_subnet(cidr, section, folder, subnet_config, description, cidr in phpipam_subnets)

def remove_prefixe_from_phpipam(sot, ipam, sync_config, where_cidr, containers):
    """remove prefixe from phpipam if prefixe are not known by sot"""

    sot_prefixe = sot.select('prefix') \
                     .using('nb.prefixes') \
                     .where(f'within_include={where_cidr}')
    
    phpipam_subnets = ipam.get_prefixe(where_cidr)
    for prefix in phpipam_subnets:
        if not any(d['prefix'] == prefix for d in sot_prefixe):
            id = phpipam_subnets[prefix]["id"]
            logger.info(f'found unknown prefix {prefix} ({id})')
            success = ipam.remove_subnet(prefix, id)
            if success:
                logger.info(f'subnet {prefix} ({id}) removed from phpipam')
            else:
                logger.info(f'could not remove subnet {prefix} ({id})')

def add_addresses_to_phpipam(sot, ipam, sync_config, where_cidr, containers):

    sot_adresses = sot.select('address, description, primary_ip4_for, name, parent') \
                     .using('nb.ipaddresses') \
                     .where(f'prefix={args.cidr}')

    for address in sot_adresses:
        addr = address.get('address')
        prefix = address.get('parent',{}).get('prefix')
        logger.debug(f'adding {addr} to prefix {prefix}')
        success = ipam.add_address(address, update=True)
        if success:
            logger.info(f'added {addr} / {prefix} successfully')
        else:
            logger.error(f'failed to add {addr} / {prefix}')

def sync_sot_to_phpipam(sot, ipam, sync_config, where_cidr, containers):
    add_prefixes_to_phpipam(sot, ipam, sync_config, where_cidr, containers)
    remove_prefixe_from_phpipam(sot, ipam, sync_config, where_cidr, containers)
    add_addresses_to_phpipam(sot, ipam, sync_config, where_cidr, containers)

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False, help="sync config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used logging handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    parser.add_argument('--cidr', type=str, required=False, default="0.0.0.0/0", help="sync all or only specified cidr")
    parser.add_argument('--create-sections', action='store_true', help='create sections')
    parser.add_argument('--create-locations', action='store_true', help='create locations')
    parser.add_argument('--create-customers', action='store_true', help='create customers')
    parser.add_argument('--sync', action='store_true', help='sync prefixe')
    parser.add_argument('--containers', action='store_true', help='add containers only')

    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    sync_config = tools.get_miniapp_config('sync_phpipam', BASEDIR, args.config)
    if not sync_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=sync_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='sync_phpipam',
        uuid=args.uuid)

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
    if args.sync:
        sync_sot_to_phpipam(sot, ipam, sync_config, args.cidr, args.containers)
