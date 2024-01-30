#!/usr/bin/env python

import asyncio
import argparse
import urllib3
import os
import sys
from loguru import logger
from icmplib import async_multiping

# veritas
import veritas.logging
from veritas.tools import tools
from veritas.sot import sot as sot


_all_hosts = {}

async def do_icmp(sot, set_link_config, addresses):
    global _all_hosts

    hosts = await async_multiping(addresses, privileged=False, count=5)
    for host in hosts:
        if not host.is_alive:
            logger.error(f'host {_all_hosts[host.address]}/{host.address} is not alive')

        hostname = _all_hosts[host.address]
        logger.debug(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
        for latency in set_link_config['defaults']['latency']:
            value = set_link_config['defaults']['latency'][latency]
            if float(host.avg_rtt) < float(value):
                logger.info(f'{hostname} / {host.address} avg.rtt: {host.avg_rtt} <= {value} setting to {latency}')
                sot.device(hostname).update({'custom_fields': {'link': latency}})
                break

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    devicelist = []

    parser = argparse.ArgumentParser()

    parser.add_argument('--config', type=str, default="./set_link.yaml", required=False, help="set_link config file")
    # what devices
    parser.add_argument('--devices', type=str, default="", required=False, help="query to get list of devices")
    parser.add_argument('--update', action='store_true', help='Update LINK even if it set')
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    set_link_config = tools.get_miniapp_config('set_link', BASEDIR, args.config)
    if not set_link_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=set_link_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='set_link',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=set_link_config['sot']['token'], 
                  url=set_link_config['sot']['nautobot'],
                  ssl_verify=set_link_config['sot']['ssl_verify'],
                  debug=False)

    devices = sot.select('hostname', 'primary_ip4', 'cf_link') \
                 .using('nb.devices') \
                 .where(args.devices)

    for device in devices:
        hostname = device.get("hostname")
        link = device.get('custom_field_data',{}).get('link','unknown')
        if link != 'unknown' and not args.update:
            logger.info(f'skipping {hostname}, link set to {link} and update not active')
            continue
        primary = device.get('primary_ip4',{}).get('address')
        primary_ip = primary.split('/')[0]
        if primary:
            _all_hosts[primary_ip] = device.get("hostname")
            devicelist.append(primary_ip)
        else:
            logger.error(f'got no primary ip for {device.get("hostname")}')

    # now ping devices and set custom field
    if len(devicelist) > 0:
        host = asyncio.run(do_icmp(sot, set_link_config, devicelist))

