import logging
import re

def device_pre_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config):
    device_fqdn = device_properties.get('name')

    # site has three digits like 001
    name = device_properties.get('site',{}).get('name')
    if name is not None:
        p = re.compile("^(?P<alpha>(k|K))(?P<digits>\d+)")
        m = p.search(slug)
        if m and len(m.group('digits')) < 3:
            device_properties['site']['name'] = "%s%03d" % (m.group('alpha'),
                                                            int(m.group('digits')))

def device_post_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config):
    pass

