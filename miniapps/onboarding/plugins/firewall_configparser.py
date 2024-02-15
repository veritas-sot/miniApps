from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.configparser import abstract_configparser


class Firewall(abstract_configparser.Configparser):

    def __init__(self, config, platform, output_format, empty_config):
        logger.debug('initialized config parser for platform firewall')

    def get_ipaddress(self, interface):
        pass

    def get_interface_name_by_address(self, address):
        pass

    def get_interface(self, interface):
        pass

    def find_in_global(self, properties):
        pass

    def find_in_interfaces(self, properties):
        pass

@plugins.configparser('firewall')
def get_configparser(config, platform):
    parser = Firewall(config=config, platform=platform)
    return parser
