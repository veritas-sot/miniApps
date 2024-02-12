from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.onboarding import abstract_business_logic_interface as abc_bl_interface


class BusinessLogic_Interface(abc_bl_interface.BusinessLogic_Interface):
    def __init__(self, device_properties, configparser):
        logger.debug('initialiting interface business logic object')

    def post_processing(self, interfaces):
        logger.debug('post processing interface business logic')
        return interfaces

@plugins.interface_business_logic('ios')
def post_processing(device_properties, configparser):
    return BusinessLogic_Interface(device_properties, configparser)
