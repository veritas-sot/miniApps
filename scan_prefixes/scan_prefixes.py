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
from datetime import datetime
from loguru import logger
from icmplib import async_ping, async_multiping
from veritas.tools import tools
from veritas.sot import sot as sot


async def do_icmp(sot, addresses, prefix_length, scan_config, add_device, update_addr):

    hosts = await async_multiping(addresses, 
                                  privileged=scan_config.get('scan').get('privileged', False), 
                                  timeout=scan_config.get('scan').get('timeout', 1), 
                                  count=scan_config.get('scan').get('count', 1))

    dflts_addresses = scan_config.get('addresses',{})
    # set current time
    now = datetime.now()
    current_date = now.strftime('%Y-%m-%d')

    for host in hosts:
        if not host.is_alive:
            logger.bind(extra=host.address).debug(f'host {host.address} is not alive')
        else:
            hostname = get_hostname(host.address)
            logger.bind(extra=f'{host.address}/{prefix_length}').info(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
            if add_device:
                # add 'dummy' device to SOT
                interface = scan_config.get('interface')
                device = scan_config.get('devices',{}).get('default',{})
                
                # check if we find the hostname in our config
                for key, value in scan_config.get('devices',{}).items():
                    if key in hostname:
                        logger.bind(extra=f'{host.address}/{prefix_length}').debug(f'found {key} in config. Updating device properties')
                        device.update(value)

                for key, value in device.items():
                    if '__' in value:
                        logger.bind(extra=f'{host.address}/{prefix_length}').debug(f'replacing {key}/{value}')
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
                addr = {'address': f'{host.address}/{prefix_length}',
                        'description': hostname,
                        'dns_name': hostname
                    }

                # make a copy of our default values
                dflts = dict(dflts_addresses)
                for key, value in dflts.items():
                    if '__' in value:
                        dflts[key] = dflts[key].replace('__HOSTNAME__', hostname)
                        dflts[key] = dflts[key].replace('__ADDRESS__', host.address)
                        dflts[key] = dflts[key].replace('__DATE__', current_date)

                # move custom fields to its down dict
                cf_fields = {}
                for key, value in dict(dflts).items():
                    if key.startswith('cf_'):
                        cf_fields[key.replace('cf_','')] = value
                        del dflts[key]

                dflts.update({'custom_fields': cf_fields})
                addr.update(dflts)

                # get IP address from sot
                ipam_addr = sot.ipam.get_ip(address=host.address)
                if ipam_addr:
                    # got IP; we need to update
                    if update_addr:
                        response = ipam_addr.update(data=addr)
                        logger.bind(extra=f'{host.address}/{prefix_length}').info(f'updated address IN SOT ({response})')
                    else:
                        logger.bind(extra=f'{host.address}/{prefix_length}').debug(f'ip is alive but we have nothing to do')
                else:
                    # new address; add it to our sot
                    logger.bind(extra=f'{host.address}/{prefix_length}').info(f'adding address to SOT')
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
    urllib3.disable_warnings()

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
                                   args.add_device,
                                   args.update))
