import re
from loguru import logger

# veritas
from veritas.plugin import configmanagement
from veritas.tools import tools


@configmanagement("postprocessing")
def postprocessing(*args, **kwargs):
    new_config = []
    removed_users = []
    logger.debug('postprocessing called...')
    properties = tools.convert_arguments_to_properties(args, kwargs)
    host_vars = properties.get('host_vars', {})
    old_config = host_vars.get('current_config', {}).get('username',[])
    new_users = host_vars.get('aaa', {}).get('users', {})
    for config in old_config:
        match = re.search('username (\w+) .*', config)
        if match:
            existing_username = match.group(1)
        if any(d['username'] ==  existing_username for d in new_users):
            logger.debug(f'user {existing_username} found in config')
        else:
            removed_users.append('no ' + config)

    # now add new users
    for user in new_users:
        new_config.append(f'username {user["username"]} privilege {user["privilege"]} secret {user["secret"]}')

    logger.bind(extra="preproc").debug(f'new_config: {new_config}')
    logger.bind(extra="preproc").debug(f'removed_users: {removed_users}')

    return removed_users + new_config