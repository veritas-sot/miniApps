from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.configparser import abstract_configparser


class Linux(abstract_configparser.Configparser):

    def __init__(self, config, platform):
        # The configuration was retrieved from the "config_and_facst" plugin.
        self._config = config
        self._platform = platform

        logger.debug('initialized config parser for platform linux')

    def get_interface_ipaddress(self, interface):
        pass

    def get_interface_name_by_address(self, address):
        pass

    def get_interface(self, interface):
        pass

    def find_in_global(self, properties):
        pass

    def find_in_interfaces(self, properties):
        pass

    def get_fqdn(self):
        return self._config.get('fqdn')

@plugins.configparser('linux')
def get_configparser(config, platform):
    parser = Linux(config=config, platform=platform)
    return parser
