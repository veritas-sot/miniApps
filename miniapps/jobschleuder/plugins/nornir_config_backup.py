import os
import yaml
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv
from nornir_napalm.plugins.tasks import napalm_get
from nornir_utils.plugins.tasks.files import write_file
from nornir_salt.plugins.functions import ResultSerializer

# veritas
import database_handling
import veritas.profile
from veritas.sot import sot as veritas_sot
from veritas.plugin import jobschleuder
from veritas.tools import tools


@jobschleuder("nornir_config_backup")
def nornir_config_backup(*args, **kwargs):

    devices = kwargs.get('where')
    sot = kwargs.get('sot')
    profile = kwargs.get('profile')
    local_config_file = kwargs.get('local_config_file')

    connection_options={'napalm': {
                          'extra': {
                            'optional_args': {
                                'conn_timeout':60, 'timeout': 60
                            }
                          }
                        },
                          'netmiko': {
                            'timeout': 60,
                            'auth_timeout': 60,
                            'read_timeout': 60,
                            'read_timeout_override': 60
                          }
                        }

    # init nornir
    nr = sot.job.on(devices) \
        .set(profile=profile, result='result', parse=False, logging={'log_file': 'session.log', 'level': 'DEBUG'}) \
        .init_nornir(connection_options=connection_options)

    result = nr.run(
            name="backup_config", 
            task=backup_config, 
            path=local_config_file.get('backup_dir','./device_configs'),
            host_dirs=local_config_file.get('individual_hostdir',True)
    )

    serialized_result = ResultSerializer(result, add_details=True)
    cursor = database_handling.connect_to_db(local_config_file.get('database'))
    for host in serialized_result:
        #print(json.dumps(serialized_result.get(host), indent=4))
        host_result = serialized_result.get(host)
        # we set the default to True because if we do not get the value something went wrong
        overall_result = host_result.get('backup_config',{}).get('failed', True)
        get_config_result = host_result.get('get_config',{}).get('failed', True)
        write_startup_config = host_result.get('write_startup_config',{}).get('failed', True)
        write_running_config = host_result.get('write_running_config',{}).get('failed', True)

        if overall_result or get_config_result or write_startup_config or write_running_config:
            logger.error(f'backup failed for {host}')
        else:
            logger.success(f'backup successful for {host}')

        database_handling.update_operating_database(
            cursor,
            host, 
            not write_running_config, 
            not write_startup_config)

    cursor.close()
    logger.info('job finished')
    logger.info(' [*] Waiting for messages. To exit press CTRL+C')

@jobschleuder("nornir_config_backup:on_startup")
def init():

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    filename = './conf/nornir_config_backup.yaml'
    with open(filename) as f:
        logger.debug(f'reading config file: {filename}')
        local_config_file = yaml.safe_load(f.read())

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=False)

    # load profiles
    profile_config = tools.get_miniapp_config('jobschleuder', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=local_config_file.get('profile',None),
        username=local_config_file.get('username',None),
        password=local_config_file.get('password',None),
        ssh_key=local_config_file.get('ssh_key',None))

    return {'profile': profile, 'local_config_file': local_config_file, 'sot': sot}

def get_profile(profile, username, password, ssh_key=None):
    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('jobschleuder', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file found and no salt.yaml file found')
            return
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # load profiles
    profile_config = tools.get_miniapp_config('jobschleuder', BASEDIR, 'profiles.yaml')
    # save profile for later use
    return veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=profile,
        username=username,
        password=password,
        ssh_key=ssh_key)

def backup_config(task, path, host_dirs, set_timestamp=False):

    dt = ""
    hostname = str(task.host)

    # Task 1. get configs from device
    logger.bind(extra=hostname).info('getting config')
    response = task.run(
        name="get_config",
        task=napalm_get, 
        getters=['config'], 
        retrieve="all"
    )
    running_config = response[0].result.get('config',{}).get('running')
    startup_config = response[0].result.get('config',{}).get('startup')

    # get current date and time
    if set_timestamp:
        now = datetime.now()
        dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'

    # use individual host directories?
    if host_dirs:
        prefix = f'{path}/{task.host}/{task.host}{dt}'
        if not os.path.exists(f'{path}/{task.host}/'):
            os.makedirs(f'{path}/{task.host}/')
    else:
        prefix = f'{path}/{task.host}{dt}'

    # modify startup config
    # on some cisco switches the startup config begins with Using xx out of yy bytes
    if startup_config.startswith('Using '):
        startup_config = startup_config.split('\n',1)[1]

    # Task 2. Write startup config to file
    logger.bind(extra=hostname).info(f'writing startup_config to {path}')
    task.run(
        name="write_startup_config",
        task=write_file,
        content=startup_config,
        filename=f'{prefix}.startup.cfg'
    )

    # Task 3. Write running config to file
    logger.bind(extra=hostname).info(f'writing running_config to {path}')
    task.run(
        name="write_running_config",
        task=write_file,
        content=running_config,
        filename=f'{prefix}.running.cfg'
    )
