from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.onboarding import abstract_business_logic_config_context as abc_bl_config_context


class BusinessLogic_ConfigContext(abc_bl_config_context.BusinessLogic_ConfigContext):
    def __init__(self, device_properties, device_facts, interfaces, configparser):
        logger.debug('initialiting config context business logic object')

    def post_processing(self, config_context):
        logger.debug('post processing config context business logic')

@plugins.config_context_business_logic('ios')
def post_processing(device_properties, device_facts, interfaces, configparser):
    return BusinessLogic_ConfigContext(device_properties, device_facts, interfaces, configparser)
