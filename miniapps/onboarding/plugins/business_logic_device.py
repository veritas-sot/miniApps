from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.onboarding import abstract_business_logic_device as abc_bl_device


class BusinessLogic_Device(abc_bl_device.BusinessLogic_Device):
    def __init__(self, configparser, device_facts):
        logger.debug('initialiting interface business logic object')

    def pre_processing(sot, device_defaults):
        logger.debug('pre_processing device business logic')

        #
        # example code to illustrate how to modify the device properties
        #

        location has three digits like 001
        name = device_defaults.get('location',{}).get('name')
        if name is not None:
            p = re.compile("^(?P<alpha>(k|K))(?P<digits>\d+)")
            m = p.search(slug)
            if m and len(m.group('digits')) < 3:
                device_defaults['location']['name'] = "%s%03d" % (m.group('alpha'),
                                                                int(m.group('digits')))

    def post_processing(sot, device_properties):
        logger.debug('post_processing device business logic')
        pass

@plugins.device_business_logic('ios')
def device_business_logic(configparser, device_facts):
    return BusinessLogic_Device(configparser, device_facts)
