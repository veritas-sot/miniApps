#!/usr/bin/env python

import asyncio
import argparse
import logging
import json
import yaml
import urllib3
import datetime
import ipaddress
import socket
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
            logging.debug(f'host {host.address} is not alive')
        else:
            hostname = get_hostname(host.address)
            logging.info(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
            if add_device:
                # add 'dummy' device to SOT
                interface = scan_config.get('interface')
                device = scan_config.get('devices',{}).get('default',{})
                
                # check if we find the hostname in our config
                for key, value in scan_config.get('devices',{}).items():
                    if key in hostname:
                        logging.debug(f'found {key} in config. Updating device properties')
                        device.update(value)

                for key, value in device.items():
                    if '__' in value:
                        logging.debug(f'replacing {key}/{value}')
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
                logging.info(f'adding address {host.address} to SOT')
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
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="set_snmp loglevel")
    # parse arguments
    args = parser.parse_args()

    # read config file
    with open(args.config) as f:
        scan_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(scan_config, ['general', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(scan_config, ['general', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(scan_config, ['general', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)#, filename=logfile)

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
        logging.info(f'pinging {subnet}')
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
