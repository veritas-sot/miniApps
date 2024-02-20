from loguru import logger

# veritas
from veritas.plugin import kobold
from veritas.tools import tools


@kobold("return_value")
def set_value_example(*args, **kwargs):
    properties = tools.convert_arguments_to_properties(args, kwargs)
    logger.debug('doing something')
    return "test"
