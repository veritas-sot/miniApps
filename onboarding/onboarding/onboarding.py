import argparse
import sys
import pytricia
import yaml
import socket
import os
import json
from loguru import logger
from slugify import slugify
from dotenv import load_dotenv, dotenv_values
from collections import defaultdict
from veritas.sot import sot as sot
from veritas.tools import tools
from onboarding import interfaces as onboarding_interfaces
from onboarding import devices as onboarding_devices
from onboarding import config_context as onboarding_config_context
from onboarding import cables as onboarding_cables
from onboarding import tags as onboarding_tags


def onboarding(sot, args, device_facts, configparser, onboarding_config, device_defaults):
    """onboard new devices to nautobot
    
    --onboarding --primary-only 
        => add new device and primary interface to SOT 
    --onboarding --interfaces
        => add new device and ALL interfaces to SOT
    --onboarding --primary-only --update 
        => update device and primary interface
    --onboarding --interfaces --update 
        => update device and all interfaces - add interfaces if not present otherwise update interfaces
    """

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
        device_fqdn = configparser.get_fqdn()

    # set extra parameter to logger
    logger.configure(extra={"extra": device_fqdn})

    # set the name of the device
    if device_fqdn:
        device_defaults['name'] = device_fqdn

    # get the "real" primary address of the device
    # the primary address is the ip address of the 'default' interface.
    # in most cases this is the Loopback or the Management interface
    # the interfaces we look at can be configured in our onboarding config
    primary_address = get_primary_address(device_fqdn,
                                          onboarding_config['onboarding']['defaults']['interface'],
                                          configparser)
    if primary_address is not None:
        logger.info(f'primary address is {primary_address}')
    else:
        # no primary interface found. Get IP of the device
        primary_address = socket.gethostbyname(device_facts['args.device'])
        logger.info("no primary ip found using %s" % device_facts['args.device'])

    # now onboard the device
    if args.onboarding:
        logger.info(f'geting device properties')
        device_properties = onboarding_devices.get_device_properties(sot,
                                                                     device_fqdn,
                                                                     device_facts,
                                                                     configparser,
                                                                     device_defaults,
                                                                     onboarding_config)
        # get vlan properties
        if args.interfaces or args.primary_only:
            logger.info(f'getting VLAN properties')
            vlan_properties = onboarding_interfaces.get_vlan_properties(device_fqdn,
                                                                        configparser,
                                                                        device_defaults)

        # the primary interface can be overwritten by our "additional" feature or the business logic
        primary_interface = device_properties['primary_interface'] \
            if 'primary_interface' in device_properties \
            else onboarding_interfaces.get_primary_interface(primary_address, configparser)
        if args.primary_only:
            logger.debug(f'adding primary interface to list of interfaces')
            interfaces = [{'name': primary_interface.get('name'),
                           'ip_addresses': [{'address': primary_interface.get('ip'),
                                             'status': {'name': 'Active'}
                                            }],
                           'description': primary_interface.get('description','Primary Interface'),
                           'type': primary_interface.get('type', '1000base-t'),
                           'status': {'name': 'Active'}}]
        elif args.interfaces:
            logger.info(f'getting interfaces properties')
            interfaces = onboarding_interfaces.get_interface_properties(sot,
                                                                        device_fqdn,
                                                                        device_facts,
                                                                        device_defaults,
                                                                        configparser)
        else:
            logger.info(f'no interfaces found')
            interfaces = []

        # we have to "adjust" the device properties
        extend_device_properties(device_properties)

        # The user can configure tags through the "Inventory". 
        # In this case, we need to convert tags into a list.
        tags = device_properties.get('tags')
        if isinstance(tags, str):
            device_properties['tags'] = tags.split(',')

        # we have all data we need to onboard the device
        # last but not least we have to check if some keys must be splitted
        # into a nested dict for example if the user sets a location using
        # location__name and location__parent__name

        nested_values = {}
        for key,value in dict(device_properties).items():
            if '__' in key:
                splitted = key.split('__')
                new_value = {}
                tools.set_value(nested_values, key, value)
                del device_properties[key]
        
        if len(nested_values) > 0 and isinstance(device_properties[splitted[0]], dict): 
                device_properties.update(nested_values)
        elif len(nested_values) > 0:
            # print warning; we cannot update the device_properties without loosing
            # the old value
            logger.warning(f'found other value than dict in device_properties[{splitted[0]}]')

        # at this point the new device was NOT added to our SOT yet
        # we have either the primary interface or all interfaces and all vlans
        # now add device or update it

        # if the device is alredy in our SOT and arg.update is not set, the main
        # script has skipped this device
        if not device_facts['is_in_sot']:
            logger.debug(f'device not found in SOT; adding it')
            # add new device to SOT
            new_device = sot.onboarding \
                .interfaces(interfaces) \
                .vlans(vlan_properties) \
                .primary_interface(primary_interface.get('name')) \
                .add_prefix(False) \
                .add_device(device_properties)
        else:
            # update device properties; the device exists and args.update is set
            device_in_nb = device_facts.get('device_in_nb')
            if not device_in_nb:
                new_device = sot.get.device(name=device_fqdn)
            else:
                new_device = device_facts.get('device_in_nb')

            if not new_device:
                logger.error(f'could not get device {device_fqdn} from SOT')
                return
            else:
                logger.debug(f'updating device properties')
                new_device.update(device_properties)

            if args.interfaces or args.primary_only:
                # get ALL interfaces of our device
                all_interfaces = sot.get.interfaces(device_id=new_device.id)

            if args.interfaces:
                # if args.interfaces is set we add unknown interfaces to SOT
                # and update ALL known interfaces as well
                new_interfaces = []
                for interface in interfaces:
                    interface_name = interface.get('name','')
                    found = False
                    for nb_interface in all_interfaces:
                        if interface_name == nb_interface.display:
                            found = True
                            response = nb_interface.update(interface)
                            logger.info(f'updating interface {interface_name}; response: {response}')
                    if not found:
                        logger.debug(f'interface {interface_name} not found in SOT')
                        new_interfaces.append(interface)
                if len(new_interfaces) > 0:
                    response = sot.onboarding \
                        .add_prefix(False) \
                        .assign_ip(True) \
                        .add_interfaces(device=new_device, interfaces=new_interfaces)
                    logger.info(f'adding {len(new_interfaces)} interface; response: {response}')

            elif args.primary_only:
                # update primary interface
                for interface in interfaces:
                    interface_name = interface.get('name','')
                    primary_interface_found = False
                    for nb_interface in all_interfaces:
                        if interface_name == nb_interface.display:
                            primary_interface_found = True
                            # response = nb_interface.update(interface)
                            response = sot.onboarding \
                                          .add_prefix(False) \
                                          .assign_ip(True) \
                                          .update_interfaces(device=new_device, interfaces=interfaces)
                            logger.info(f'updating primary interface {interface_name}; response: {response}')
                    if not primary_interface_found:
                        logger.debug(f'no primary inteface found; seems to be a new one; adding it')
                        response = sot.onboarding \
                                       .add_prefix(False) \
                                       .assign_ip(True) \
                                       .add_interfaces(device=new_device, interfaces=interfaces)

            # maybe the primary IP has changed. Check it and update if necessary
            if new_device.primary_ip4:
                current_primary_ip = new_device.primary_ip4.display.split('/')[0]
            else:
                # there is no primary IP
                current_primary_ip = "unknown or none"
                logger.debug(f'the device {new_device.display} has no primary IP configured; setting it now')
            if current_primary_ip != primary_address:
                logger.info(f'updating primary IP of device {new_device.display} {current_primary_ip} vs. {primary_address}')
                sot.onboarding.set_primary_address(primary_address, new_device)

    if args.tags:
        logger.info("getting tag properties")
        tag_properties = onboarding_tags.to_sot(sot,
                                                args,
                                                device_fqdn,
                                                device_defaults,
                                                device_facts,
                                                configparser,
                                                onboarding_config)

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
            logger.debug(f'adding device tags successfully')
        else:
            logger.error(f'adding device tags failed')

        # add interface scope tags
        for interface_name in interface_tags:
            iface = sot.get.interface(device_id=new_device.id, 
                                        name=interface_name)
            result = iface.update({'tags': interface_tags[interface_name]})
            if result:
                logger.debug(f'adding interface tag successfully')
            else:
                logger.error(f'adding interface tag failed')

    # # now the most import part: the config_context
    # # do your own business logic in the "businesslogic" subdir
    # if args.config_context or args.write_hldm or args.show_hldm:
    #     logger.info("onboarding config context")
    #     cc = onboarding_config_context.to_sot(sot,
    #                                           args,
    #                                           device_fqdn,
    #                                           configparser,
    #                                           device_defaults,
    #                                           onboarding_config)
    #     hldm['config_context'] = cc

    # # at last do a backup of the running config
    # if args.backup:
    #     logger.info("onboarding backup")
    #     onboarding_devices.backup_config(sot,
    #                                      device_fqdn,
    #                                      configparser.get_device_config(),
    #                                      onboarding_config)


def get_primary_address(device_fqdn, interfaces, cisco_config):
    for iface in interfaces:
        if cisco_config.get_ipaddress(iface) is not None:
            return cisco_config.get_ipaddress(iface)
        else:
            logger.debug(f'no ip address on {iface} found')

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
