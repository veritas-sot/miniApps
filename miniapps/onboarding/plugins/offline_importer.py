import os
from ipaddress import IPv4Network
from loguru import logger

# veritas
from veritas.onboarding import plugins


@plugins.offline_importer
def offline_onboarding(device_ip, device_defaults, onboarding_config):
    """set device_facts and device_defaults, build device config and return config and platform"""

    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # at the beginning we have no device_config
    device_config = None
    hostname = device_defaults.get('name')

    # we do not have any facts
    model = device_defaults.get('model', 
            onboarding_config['onboarding']['offline_config'].get('model','unknown'))
    serial = device_defaults.get('serial', 
                onboarding_config['onboarding']['offline_config'].get('serial',''))
    manufacturer = device_defaults.get('manufacturer', 
                    onboarding_config['onboarding']['offline_config'].get('manufacturer','cisco'))
    platform = device_defaults.get('platform', 
                    onboarding_config['onboarding']['offline_config'].get('platform','ios'))
    primary_interface = device_defaults.get('primary_interface', 
                    onboarding_config['onboarding']['offline_config'].get('primary_interface','primary_interface'))
    primary_description = device_defaults.get('primary_description', 
                    onboarding_config['onboarding']['offline_config'].get('primary_description','Primary Interface'))
    primary_mask = device_defaults.get('primary_mask', 
                    onboarding_config['onboarding']['offline_config'].get('primary_mask','255.255.255.255'))
    # we need cidr notation
    primary_ipv4 = IPv4Network(f'{device_ip}/{primary_mask}', strict=False)
    primary_cidr = f'{device_ip}/{primary_ipv4.prefixlen}'
    # the format of device_properties['primary_interface'] is:
    # {'ip': '192.168.0.2/32', 'mask': '255.255.255.255', 'name': 'primary_interface', 'description': 'primary interface'}

    # check if we have a dict or a string
    # we need the NAME of the primary interface and not a dict
    if isinstance(primary_interface, dict):        
        primary_interface_name = primary_interface.get('name','primary_interface')
    else:
        primary_interface_name = primary_interface

    offline_primary_interface = {
        'address': primary_cidr,
        'mask': primary_mask,
        'name': primary_interface_name,
        'description': primary_description
    }
    device_facts = {
        "manufacturer": manufacturer,
        "model": model,
        "serial_number": serial,
        "hostname": hostname,
        "fqdn": hostname,
        "device_ip": device_ip
    }

    for key, value in offline_primary_interface.items():
        if key in device_defaults['primary_interface']:
            logger.bind(extra='off (=)').trace(f'key=primary_interface.{key} value={value}')
        else:
            logger.bind(extra='off (+)').trace(f'key=primary_interface.{key} value={value}')
        device_defaults['primary_interface'][key] = value

    if 'config' in device_defaults:
        # should we use a local device config?
        if device_defaults.get('config').lower() == 'none':
            # no config at all / use minimal default config
            logger.debug('no offline config found; use minimal config')
            device_config = f'hostname {hostname}\n'
            device_config += f'interface {primary_interface_name}\n'
            device_config += f' ip address {device_ip} {primary_mask}\n'
            offline_config = False
        else:
            # yes, the name of the config was configured by the inventory
            logger.debug(f'using offline config {device_defaults.get("config")}')
            offline_config = BASEDIR + "/" + device_defaults.get('config')
    else:
        # use default offline config
        logger.debug('using default offline config')
        offline_config = BASEDIR + "/" + onboarding_config['onboarding']['offline_config']['filename']

    if offline_config:
        # read offline device config
        logger.debug(f'reading offline config {offline_config}')
        try:
            with open(offline_config, 'r') as f:
                device_config = f.read()
                device_config = device_config.replace('__PRIMARY_IP__', device_ip)
                device_config = device_config.replace('__HOSTNAME__', hostname)
                device_config = device_config.replace('__PRIMARY_INTERFACE__', primary_interface_name)
                device_config = device_config.replace('__PRIMARY_MASK__', primary_mask)
        except Exception as exc:
            logger.error(f'failed to read offline config {exc}', exc_info=True)
            return {},{}, ""

    return device_config, device_facts, platform