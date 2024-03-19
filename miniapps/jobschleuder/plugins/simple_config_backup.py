import yaml
from loguru import logger
import os
from dotenv import load_dotenv

# veritas
import veritas.profile
import database_handling
from veritas.plugin import jobschleuder
from veritas.devicemanagement import napalm as dm
from veritas.tools import tools


@jobschleuder("simple_config_backup")
def simple_config_backup(*args, **kwargs):

    # get device information
    device = kwargs.get('name')
    device_ip = kwargs.get('primary_ip4', device)
    platform = kwargs.get('platform','ios')
    manufacturer = kwargs.get('manufacturer','cisco')
    tcp_port = kwargs.get('tcp_port', 22)
    backup_dir = kwargs.get('backup_dir')

    # get profile
    profile = kwargs.get('profile')
    if profile:
        username =  profile.username
        password = profile.password
        ssh_keyfile = profile.ssh_key
    
    # we need at least a username or a ssh_keyfile
    if not username and not ssh_keyfile:
        logger.critical('job failed; no username or ssh_keyfile specified')
        return

    # we need a backup directory
    if not backup_dir:
        logger.critical('job failed; no backup dir specified')
        return
    else:
        backup_dir = f'{backup_dir}/{device}'

    # now process the device
    if device:
        logger.bind(extra="backup").info(f'backup device: {device} ({device_ip})')

        try:
            conn_to_device = dm.Devicemanagement(
                    ip=device_ip,
                    platform=platform,
                    manufacturer=manufacturer,
                    username=username,
                    password=password,
                    ssh_keyfile=ssh_keyfile,
                    port=tcp_port)
            
            conn = conn_to_device.open()
            if not conn:
                logger.critical(f'failed to connect to {device}')
                startup_config = running_config = None
            else:
                configs = conn.get_config()
                conn.close()
                startup_config = configs['startup']
                running_config = configs['running']
        except Exception as exc:
            logger.error(f'could not connect to {device_ip}')
            startup_config = running_config = None

        if startup_config and len(startup_config) < 100:
            logger.error(f'failed to get startup config for {device}')
            startup_config = None
        if running_config and len(running_config) < 100:
            logger.error(f'failed to get running config for {device}')
            running_config = None

        # check if backup_dir directory exists and write runnnig and startup config to it
        if not os.path.isdir(backup_dir):
            # directory does not exist; create it
            logger.info(f'backup directory {backup_dir} does not exist')
            try:
                os.makedirs(backup_dir)
                logger.info(f'created backup directory {backup_dir}')
            except Exception as exc:
                logger.error(f'failed to create backup directory {backup_dir}; got exception {exc}')
                return

        success_running = False
        success_startup = False

        if running_config:
            with open(f'{backup_dir}/{device}.running.cfg', 'w') as f:
                logger.info(f'writing running config to {backup_dir}/{device}.running.cfg')
                f.write(running_config)
                success_running = True

        if startup_config:
            with open(f'{backup_dir}/{device}.startup.cfg', 'w') as f:
                logger.info(f'writing startup config to {backup_dir}/{device}.startup.cfg')
                f.write(startup_config)
                success_startup = True

        if running_config and startup_config:
            logger.success(f'backup successful for {device}')
        else:
            logger.error(f'backup failed for {device}')

        cursor = database_handling.connect_to_db(kwargs.get('database'))
        database_handling.update_operating_database(
            cursor,
            device, 
            success_running, 
            success_startup)
        cursor.close()

@jobschleuder("simple_config_backup:on_startup")
def init():
    # read config
    filename = './conf/simple_config_backup.yaml'
    # check if file exists and read it
    if os.path.isfile(filename):
        with open(filename) as f:
            logger.debug(f'reading config file: {filename}')
            config = yaml.safe_load(f.read())
    else:
        logger.error(f'failed to read config file: {filename}')
        return {}

    # get profile
    username = config.get('username')
    password = config.get('password')
    profile = config.get('profile')
    ssh_key = config.get('ssh_key')
    profile = get_profile(profile, username, password, ssh_key)

    if not profile and not username:
        logger.error('no profile or username specified')
        return config

    config['profile'] = profile
    return config

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
