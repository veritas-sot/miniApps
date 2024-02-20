import asyncio
from loguru import logger
from icmplib import async_multiping

# veritas
from veritas.plugin import kobold
from veritas.tools import tools


_all_hosts = {}


def set_link_of_device(sot, custom_field, latency_config, update, devices):

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
        asyncio.run(do_icmp(sot, latency_config, devicelist))

async def do_icmp(sot, latency_config, addresses):
    global _all_hosts

    hosts = await async_multiping(addresses, privileged=False, count=5)
    for host in hosts:
        if not host.is_alive:
            logger.error(f'host {_all_hosts[host.address]}/{host.address} is not alive')

        hostname = _all_hosts[host.address]
        logger.debug(f'avg. latency of {hostname}/{host.address}: {host.avg_rtt}')
        for latency in latency_config:
            value = latency_config[latency]
            logger.debug(f'host.avg_rtt: {host.avg_rtt} value: {value} latency: {latency}')
            if float(host.avg_rtt) < float(value):
                logger.info(f'{hostname} / {host.address} avg.rtt: {host.avg_rtt} <= {value} setting to {latency}')
                sot.device(hostname).update({'custom_fields': {'link': latency}})
                break

@kobold("set_link")
def set_link(*args, **kwargs):
    properties = tools.convert_arguments_to_properties(args, kwargs)

    sot = properties.get('sot')
    arguments = properties.get('arguments')
    devices = properties.get('devices')

    update = arguments.get('update', False)
    custom_field = arguments.get('custom_field', 'latency')
    latency_config = arguments.get('latency', {})

    set_link_of_device(sot, custom_field, latency_config, update, devices)
