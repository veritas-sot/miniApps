#!/usr/bin/env python

import asyncio
import argparse
import json
import yaml
import urllib3
import datetime
import ipaddress
import socket
import sys
import os
from loguru import logger
from icmplib import async_ping, async_multiping
from veritas.tools import tools
from veritas.sot import sot as sot


async def do_icmp(sot, addresses, prefix_length, scan_config, add_device):

    hosts = await async_multiping(addresses, 
                                  privileged=scan_config.get('scan').get('privileged', False), 
                                  timeout=scan_config.get('scan').get('timeout', 1), 
                                  count=scan_config.get('scan').get('count', 1))
    for host in hosts:
        if not host.is_alive:
            logger.debug(f'host {host.address} is not alive')
        else:
            hostname = get_hostname(host.address)
            logger.info(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
            if add_device:
                # add 'dummy' device to SOT
                interface = scan_config.get('interface')
                device = scan_config.get('devices',{}).get('default',{})
                
                # check if we find the hostname in our config
                for key, value in scan_config.get('devices',{}).items():
                    if key in hostname:
                        logger.debug(f'found {key} in config. Updating device properties')
                        device.update(value)

                for key, value in device.items():
                    if '__' in value:
                        logger.debug(f'replacing {key}/{value}')
                        device[key] = device[key].replace('__HOSTNAME__', hostname)
                        device[key] = device[key].replace('__ADDRESS__', host.address)

                interface.update({'ip_addresses': [{
                                        'address': f'{host.address}/{ prefix_length}',
                                        'status': {'name': 'Active'}}]
                                 })
                new_device = sot.onboarding \
                    .interfaces(interface) \
                    .primary_interface("primary") \
                    .add_prefix(False) \
                    .assign_ip(True) \
                    .add_device(device)
            else:
                # add address only to sot
                logger.info(f'adding address {host.address} to SOT')
                addr = {'address': host.address,
                        'description': hostname,
                    }
                dflts = scan_config.get('addresses',{})
                for key, value in dflts.items():
                    if '__' in value:
                        dflts[key] = dflts[key].replace('__HOSTNAME__', hostname)
                        dflts[key] = dflts[key].replace('__ADDRESS__', host.address)
                addr.update(scan_config.get('addresses',{}))
                response = sot.ipam.add_ip(addr)

def get_hostname(ip_address):
    try:
        return socket.gethostbyaddr(ip_address)[0]
    except socket.herror:
        return ip_address


if __name__ == "__main__":
    """scan prefixes

    --prefix 'within_include="192.168.0.0/24"' or
    
    if you want to select another namespace

    --prefix 'within_include="192.168.0.0/24" and namespace=namespace' 
    """

    # to disable warning if TLS warning is written to console
    # urllib3.disable_warnings()

    devicelist = []

    parser = argparse.ArgumentParser()

    parser.add_argument('--config', type=str, default="./scan_prefixes.yaml", required=False, help="scan_prefixes config file")
    # what devices
    parser.add_argument('--prefix', type=str, default="", required=False, help="query to get prefixes")
    parser.add_argument('--update', action='store_true', help='Update address')
    parser.add_argument('--add-device', action='store_true', help='Add device to SOT')
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # parse arguments
    args = parser.parse_args()

    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    scan_config = tools.get_miniapp_config('scan_prefixes', BASEDIR, args.config)
    if not scan_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    tools.create_logger_environment(scan_config, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=scan_config['sot']['token'], url=scan_config['sot']['nautobot'])
    prefixes = sot.select('prefix') \
                  .using('nb.prefixes') \
                  .where(args.prefix)

    subnets = []
    for prefix in prefixes:
        subnets.append(prefix.get('prefix'))

    address = []
    for subnet in subnets:
        logger.info(f'pinging {subnet}')
        prefix_length = subnet.split('/')[1]
        network = ipaddress.ip_network(subnet, strict=False)
        for ip in network.hosts():
            # our call needs a LIST of addresses!!!
            address.append(str(ip))
        host = asyncio.run(do_icmp(sot, 
                                   address, 
                                   prefix_length, 
                                   scan_config, 
                                   args.add_device))
