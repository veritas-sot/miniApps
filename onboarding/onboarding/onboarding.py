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

    # if args.tags:
    #     logging.info("onboarding tags")
    #     tags = onboarding_tags.to_sot(sot,
    #                                   args,
    #                                   device_fqdn,
    #                                   device_defaults,
    #                                   device_facts,
    #                                   configparser)

    if args.onboarding:
        # get vlan properties
        if args.interfaces or args.primary_only:
            logging.info(f'get VLAN properties of {device_fqdn}')
            vlan_properties = onboarding_interfaces.get_vlan_properties(device_fqdn,
                                                                        configparser,
                                                                        device_defaults)
        primary_interface = device_properties['primary_interface'] \
            if 'primary_interface' in device_properties \
            else onboarding_interfaces.get_primary_interface(primary_address, configparser)

        if args.primary_only:
            interfaces = [{'name': primary_interface.get('name'),
                           'ipv4': primary_address,
                           'description': primary_interface.get('description','Primary Interface'),
                           'type': primary_interface.get('type', '1000base-t'),
                           'status': {'name': 'Active'}}]
        elif args.interfaces:
            logging.info(f'getting interfaces properties if {device_fqdn}')
            interfaces = onboarding_interfaces.get_interface_properties(sot,
                                                                       device_fqdn,
                                                                       device_facts,
                                                                       device_defaults,
                                                                       configparser)
        else:
            interfaces = []

        # add device to SOT
        new_device = sot.onboarding \
            .interfaces(interfaces) \
            .vlans(vlan_properties) \
            .primary_interface(primary_interface.get('name')) \
            .add_prefix(False) \
            .add_device(device_properties)

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

    # return hldm

def get_primary_address(device_fqdn, interfaces, cisco_config):
    for iface in interfaces:
        if cisco_config.get_ipaddress(iface) is not None:
            return cisco_config.get_ipaddress(iface)
        else:
            logging.debug(f'no ip address on {iface} found')

    return None
