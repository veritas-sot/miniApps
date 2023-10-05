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
    # init some vars
    hldm = {}

    # we need the fqdn of the device
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

    # check if we have all necessary defaults
    list_def = ['site', 'device_role', 'device_type', 'manufacturer', 'platform', 'status']
    for i in list_def:
        if i not in device_defaults:
            logging.error("%s missing. Please add %s to your default or set as arg" % (i, i))
            return False

    logging.debug(f'device_defaults are: {device_defaults}')

    # now lets start the onboarding process
    # first of all import the device to our sot
    if args.onboarding or args.write_hldm or args.show_hldm:
        logging.info("onboarding device")
        hldm = onboarding_devices.to_sot(sot,
                                         args,
                                         device_fqdn,
                                         device_facts,
                                         configparser,
                                         primary_address,
                                         device_defaults,
                                         onboarding_config)

    # we add the vlans before adding the physical or virtual interfaces
    # because some interfaces may be access vlans
    if args.vlans or args.write_hldm or args.show_hldm:
        logging.info("onboarding vlans")
        vlans = onboarding_interfaces.vlans(sot,
                                            args,
                                            device_fqdn,
                                            configparser,
                                            device_defaults)
        hldm['vlans'] = vlans

    # now add interfaces to sot
    if args.interfaces or args.write_hldm or args.show_hldm:
        logging.info("onboarding interfaces")
        interfaces = onboarding_interfaces.to_sot(sot,
                                                  args,
                                                  device_fqdn,
                                                  device_facts,
                                                  device_defaults,
                                                  configparser)
        hldm['interfaces'] = interfaces

    if args.tags or args.write_hldm or args.show_hldm:
        logging.info("onboarding tags")
        tags = onboarding_tags.to_sot(sot,
                                      args,
                                      device_fqdn,
                                      device_defaults,
                                      device_facts,
                                      configparser)
        hldm['tags'] = tags

    # now the most import part: the config_context
    # do your own business logic in the "businesslogic" subdir
    if args.config_context or args.write_hldm or args.show_hldm:
        logging.info("onboarding config context")
        cc = onboarding_config_context.to_sot(sot,
                                              args,
                                              device_fqdn,
                                              configparser,
                                              device_defaults,
                                              onboarding_config)
        hldm['config_context'] = cc

    # at last do a backup of the running config
    if args.backup:
        logging.info("onboarding backup")
        onboarding_devices.backup_config(sot,
                                         device_fqdn,
                                         configparser.get_device_config(),
                                         onboarding_config)

    return hldm

def get_primary_address(device_fqdn, interfaces, cisco_config):
    for iface in interfaces:
        if cisco_config.get_ipaddress(iface) is not None:
            return cisco_config.get_ipaddress(iface)
        else:
            logging.debug(f'no ip address on {iface} found')

    return None
