import logging
from slugify import slugify

def device_pre_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config):
    logging.debug("-- entering your_device.py/device_pre_processing)")
    device_fqdn = device_properties.get('name')

    # set location if city is in device_defaults
    # if 'city' in device_defaults and device_defaults['city'] is not None:
    #     logging.debug(f'adding city to location')
    #     location = {'location': {'slug': slugify(device_defaults.get('city'))}}
    #     device_properties.update(location)

def device_post_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config):
    device_fqdn = device_properties.get('name')

