from loguru import logger

# veritas
from veritas.plugin import configmanagement
from veritas.tools import tools


@configmanagement("preprocessing")
def preprocessing(*args, **kwargs):
    logger.debug('preprocessing called...')
    properties = tools.convert_arguments_to_properties(args, kwargs)
    host_vars = properties.get('host_vars', {})

    snmp = {}
    snmp_credentials = properties.get('host', {}).get('snmp_credentials',[])
    for cred in properties.get('host', {}).get('credentials',{}).get('snmp',[]):
        if cred.get('id') == snmp_credentials:
            snmp = dict(cred)
    if snmp:
        logger.bind(extra="preproc").debug(f'found snmp credentials {snmp_credentials}')
        host_vars['snmp'] = snmp

    return host_vars

@configmanagement("postprocessing")
def postprocessing(*args, **kwargs):
    logger.debug('postprocessing called...')
    properties = tools.convert_arguments_to_properties(args, kwargs)
    host_vars = properties.get('host_vars', {})

    old_config = host_vars.get('current_config', {}).get('snmp-server',[])
    remove = []
    for cmd in old_config:
        remove.append('no ' + cmd)
    if len(remove) > 0:
        logger.info('removing old SNMP config')
        logger.debug(f'sending {remove}')
        commands = remove + properties.get('commands', [])
    else:
        commands = properties.get('commands', [])
    return commands