import argparse
import sys
import pytricia
import yaml
import socket
import os
import json
import logging
from slugify import slugify
from dotenv import load_dotenv, dotenv_values
from collections import defaultdict
from veritas.sot import sot as sot
from onboarding import interfaces as onboarding_interfaces
from onboarding import devices as onboarding_devices
from onboarding import config_context as onboarding_config_context
from onboarding import cables as onboarding_cables
from onboarding import tags as onboarding_tags

def onboarding(sot, args, device_facts, configparser, onboarding_config, device_defaults):
    """onboard new devices to nautobot"""

    # we have some empty variables
    vlan_properties = []
    interface_properties = []
    tag_properties = []
    new_device = None

    # we need the FQDN of the device
    if device_facts is not None and 'fqdn' in device_facts:
        device_fqdn = device_facts['fqdn'].lower()
    else:
        # get fqdn from config instead
        device_fqdn = ciscoconf.get_fqdn().lower()

    # get the "real" primary address of the device
    # the primary address is the ip address of the 'default' interface.
    # in most cases this is the Loopback or the Management interface
    # the interfaces we look at can be configured in our onboarding config
    primary_address = get_primary_address(device_fqdn,
                                          onboarding_config['onboarding']['defaults']['interface'],
                                          configparser)
    if primary_address is not None:
        logging.info(f'primary address of {device_fqdn} is {primary_address}')
    else:
        # no primary interface found. Get IP of the device
        primary_address = socket.gethostbyname(device_facts['args.device'])
        logging.info("no primary ip found using %s" % device_facts['args.device'])

    # now lets start the onboarding process
    # first of all add the device to our sot
    if args.onboarding:
        logging.info(f'get device properties of {device_fqdn}')
        device_properties = onboarding_devices.get_device_properties(sot,
                                                                     device_fqdn,
                                                                     device_facts,
                                                                     configparser,
                                                                     device_defaults,
                                                                     onboarding_config)

    if args.tags:
        logging.info("get tags properties")
        tag_properties = onboarding_tags.to_sot(sot,
                                                args,
                                                device_fqdn,
                                                device_defaults,
                                                device_facts,
                                                configparser,
                                                onboarding_config)

    if args.onboarding:
        # get vlan properties
        if args.interfaces or args.primary_only:
            logging.info(f'get VLAN properties of {device_fqdn}')
            vlan_properties = onboarding_interfaces.get_vlan_properties(device_fqdn,
                                                                        configparser,
                                                                        device_defaults)

        # the primary interface can be overwritten by our "additional" feature or the business logic
        primary_interface = device_properties['primary_interface'] \
            if 'primary_interface' in device_properties \
            else onboarding_interfaces.get_primary_interface(primary_address, configparser)

        if args.primary_only:
            interfaces = [{'name': primary_interface.get('name'),
                           'ipv4': primary_interface.get('ip'),
                           'description': primary_interface.get('description','Primary Interface'),
                           'type': primary_interface.get('type', '1000base-t'),
                           'status': {'name': 'Active'}}]
        elif args.interfaces:
            logging.info(f'getting interfaces properties of {device_fqdn}')
            interfaces = onboarding_interfaces.get_interface_properties(sot,
                                                                       device_fqdn,
                                                                       device_facts,
                                                                       device_defaults,
                                                                       configparser)
        else:
            interfaces = []

        # we have to "adjust" the device properties
        extend_device_properties(device_properties)

        # add device to SOT
        if not device_facts['is_in_sot']:
            new_device = sot.onboarding \
                .interfaces(interfaces) \
                .vlans(vlan_properties) \
                .primary_interface(primary_interface.get('name')) \
                .add_prefix(False) \
                .add_device(device_properties)
        # or update device properties if device exists and args.update
        elif args.update:
            new_device = device_facts.get('device_in_nb', sot.get.device(name=device_fqdn))
            if not new_device:
                logging.error(f'could not get device {device_fqdn} from SOT')
                return
            else:
                logging.debug(f'updating device properties of {device_fqdn}')
                new_device.update(device_properties)

    if args.tags:
        if not new_device:
            new_device = device_facts.get('device_in_nb', sot.get.device(name=device_fqdn))
        device_tags = []
        interface_tags = {}
        for tag in tag_properties:
            if tag.get('scope') == 'dcim.device':
                device_tags.append({'name': tag.get('name')})
            if tag.get('scope') == 'dcim.interface':
                interface_name = tag.get('interface')
                if interface_name not in interface_tags:
                    interface_tags[interface_name] = []
                interface_tags[interface_name].append({'name': tag.get('name')})

        # add device scope tags
        result = new_device.update({'tags': device_tags})
        if result:
            logging.debug(f'adding device tags successfully')
        else:
            logging.error(f'adding device tags failed')

        # add interface scope tags
        for interface_name in interface_tags:
            iface = sot.get.interface(device_id=new_device.id, 
                                        name=interface_name)
            result = iface.update({'tags': interface_tags[interface_name]})
            if result:
                logging.debug(f'adding interface tag successfully')
            else:
                logging.error(f'adding interface tag failed')

    # # now the most import part: the config_context
    # # do your own business logic in the "businesslogic" subdir
    # if args.config_context or args.write_hldm or args.show_hldm:
    #     logging.info("onboarding config context")
    #     cc = onboarding_config_context.to_sot(sot,
    #                                           args,
    #                                           device_fqdn,
    #                                           configparser,
    #                                           device_defaults,
    #                                           onboarding_config)
    #     hldm['config_context'] = cc

    # # at last do a backup of the running config
    # if args.backup:
    #     logging.info("onboarding backup")
    #     onboarding_devices.backup_config(sot,
    #                                      device_fqdn,
    #                                      configparser.get_device_config(),
    #                                      onboarding_config)


def get_primary_address(device_fqdn, interfaces, cisco_config):
    for iface in interfaces:
        if cisco_config.get_ipaddress(iface) is not None:
            return cisco_config.get_ipaddress(iface)
        else:
            logging.debug(f'no ip address on {iface} found')

    return None

def extend_device_properties(properties):
    """ we have to modify some attributes like device_type and role"""
    if 'device_type' in properties:
        properties['device_type'] = {'model': properties['device_type']}
    if 'role' in properties:
        properties['role'] = {'name': properties['role']}
    if 'manufacturer' in properties:
        properties['manufacturer'] = {'name': properties['manufacturer']}
    if 'platform' in properties:
        properties['platform'] = {'name': properties['platform']}
    if 'status' in properties:
        properties['status'] = {'name': properties['status']}
