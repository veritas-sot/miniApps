import asyncio
from loguru import logger
from icmplib import async_multiping


_all_hosts = {}


def set_link(sot, set_link_config, update, where):

    # get custom field
    custom_field = set_link_config.get('defaults',{}).get('custom_field', 'link')
    devices = sot.select('hostname', 'primary_ip4', f'cf_{custom_field}') \
                 .using('nb.devices') \
                 .where(where)

    devicelist = []
    for device in devices:
        hostname = device.get("hostname")
        link = device.get('custom_field_data',{}).get('link','unknown')
        if link != 'unknown' and not update:
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
        asyncio.run(do_icmp(sot, set_link_config, devicelist))


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
