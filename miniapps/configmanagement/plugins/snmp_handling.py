from loguru import logger

# veritas
from veritas.plugin import configmanagement


@configmanagement("preprocessing")
def preprocessing(task):
    logger.debug('preprocessing called...')

    host_vars = task.host['vars']

    snmp = {}
    snmp_credentials = task.host.get('snmp_credentials',[])
    for cred in task.host.get('credentials',{}).get('snmp',[]):
        if cred.get('id') == snmp_credentials:
            snmp = dict(cred)
    if snmp:
        logger.bind(extra="preproc").debug(f'found snmp credentials {snmp_credentials}')
        host_vars['snmp'] = snmp

    return host_vars

@configmanagement("postprocessing")
def postprocessing(task, commands:list=[]):
    logger.debug('postprocessing called...')

    host_vars = task.host['vars']

    old_config = host_vars.get('current_config', {}).get('snmp-server',[])
    remove = []
    for cmd in old_config:
        remove.append('no ' + cmd)
    if len(remove) > 0:
        logger.info('removing old SNMP config')
        logger.debug(f'sending {remove}')
        return remove + commands
    else:
        return commands
