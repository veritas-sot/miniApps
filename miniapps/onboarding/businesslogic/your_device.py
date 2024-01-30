import logging
import re

def device_pre_processing(sot, device_properties, ciscoconf, onboarding_config):
    device_fqdn = device_properties.get('name')

    # example code to illustrate how to modify the device properties

    # location has three digits like 001
    # name = device_properties.get('location',{}).get('name')
    # if name is not None:
    #     p = re.compile("^(?P<alpha>(k|K))(?P<digits>\d+)")
    #     m = p.search(slug)
    #     if m and len(m.group('digits')) < 3:
    #         device_properties['location']['name'] = "%s%03d" % (m.group('alpha'),
    #                                                         int(m.group('digits')))

def device_post_processing(sot, device_properties, ciscoconf, onboarding_config):
    pass

