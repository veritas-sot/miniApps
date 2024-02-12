from loguru import logger

# veritas
from veritas.onboarding import plugins
from veritas.tools import tools


class Firewall(object):

    def __init__(self, *unnamed, **named):
        properties = tools.convert_arguments_to_properties(unnamed, named)
        self._device_config = properties.get('config', None)
        self._output_format = properties.get('output_format', 'json')
        logger.debug('initialized config parser for platform firewall')

@plugins.configparser('firewall')
def get_configparser(config, platform):
    parser = Firewall(config=config, platform=platform)
    return parser
