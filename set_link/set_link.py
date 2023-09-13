#!/usr/bin/env python

import asyncio
import argparse
import logging
import json
import yaml
from icmplib import async_ping, async_multiping
from veritas.tools import tools
from veritas.sot import sot as sot


_all_hosts = {}

async def do_icmp(sot, set_link_config, addresses):
    global _all_hosts

    hosts = await async_multiping(addresses, privileged=False, count=5)
    for host in hosts:
        if not host.is_alive:
            logging.error(f'host {_all_hosts[host.address]}/{host.address} is not alive')

        hostname = _all_hosts[host.address]
        logging.debug(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
        for latency in set_link_config['defaults']['latency']:
            value = set_link_config['defaults']['latency'][latency]
            link_set = False
            if float(host.avg_rtt) < float(value):
                logging.info(f'{hostname} / {host.address} avg.rtt: {host.avg_rtt} <= {value} setting to {latency}')
                sot.device(hostname).update({'custom_fields': {'link': latency}})
                break

if __name__ == "__main__":

    devicelist = []

    parser = argparse.ArgumentParser()

    parser.add_argument('--config', type=str, default="./set_link.yaml", required=False, help="set_link config file")
    # what devices
    parser.add_argument('--devices', type=str, default="", required=False, help="query to get list of devices")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="set_snmp loglevel")
    # parse arguments
    args = parser.parse_args()

    # read config file
    with open(args.config) as f:
        set_link_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(set_link_config, ['general', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(set_link_config, ['general', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(set_link_config, ['general', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)#, filename=logfile)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=set_link_config['sot']['token'], url=set_link_config['sot']['nautobot'])
    devices = sot.select('hostname', 'primary_ip4') \
                .using('nb.devices') \
                .normalize(False) \
                .where(args.devices)

    for device in devices:
        primary = device.get('primary_ip4',{}).get('address')
        primary_ip = primary.split('/')[0]
        if primary:
            _all_hosts[primary_ip] = device.get("hostname")
            devicelist.append(primary_ip)
        else:
            logging.error(f'git no primary ip for {device.get("hostname")}')

    # now ping devices and set custom field
    host = asyncio.run(do_icmp(sot, set_link_config, devicelist))

