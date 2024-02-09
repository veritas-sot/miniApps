import asyncio
from loguru import logger
from icmplib import async_multiping


_all_hosts = {}


def set_latency(sot, set_latency_config, update, where):

    # get custom field
    custom_field = set_latency_config.get('defaults',{}).get('custom_field', 'latency')
    devices = sot.select('hostname', 'primary_ip4', f'cf_{custom_field}') \
                 .using('nb.devices') \
                 .where(where)

    devicelist = []
    for device in devices:
        hostname = device.get("hostname")
        latency = device.get('custom_field_data',{}).get(custom_field,'unknown')
        if latency and latency != 'unknown' and not update:
            logger.info(f'skipping {hostname}, latency is {latency} and update not active')
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
        asyncio.run(do_icmp(sot, custom_field, devicelist))

async def do_icmp(sot, custom_field, addresses):
    global _all_hosts

    hosts = await async_multiping(addresses, privileged=False, count=5)
    for host in hosts:
        if not host.is_alive:
            logger.error(f'host {_all_hosts[host.address]}/{host.address} is not alive')

        hostname = _all_hosts[host.address]
        logger.info(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
        sot.device(hostname).update({'custom_fields': {custom_field: str(host.avg_rtt)}})
