import yaml
from loguru import logger
import os
import psycopg2
import psycopg2.extras

# veritas
from veritas.plugin import jobschleuder
from veritas.devicemanagement import napalm as dm


@jobschleuder("simple_config_backup")
def simple_config_backup(*args, **kwargs):

    # get device information
    device = kwargs.get('name')
    device_ip = kwargs.get('primary_ip4', device)
    platform = kwargs.get('platform','ios')
    manufacturer = kwargs.get('manufacturer','cisco')
    tcp_port = kwargs.get('tcp_port', 22)
    username = kwargs.get('username')
    password = kwargs.get('password')
    ssh_keyfile = kwargs.get('ssh_keyfile', None)
    backup_dir = kwargs.get('backup_dir')

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
            return
        configs = conn.get_config()
        conn.close()
        startup_config = configs['startup']
        running_config = configs['running']

        if len(startup_config) < 100:
            logger.error(f'failed to get startup config for {device}')
            startup_config = None
        if len(running_config) < 100:
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
        
        update_operating_database(device, success_running, success_startup, kwargs.get('database'))

@jobschleuder("simple_config_backup:on_startup")
def init():
    # read config
    filename = './conf/simple_config_backup.yaml'
    # check if file exists and read it
    if os.path.isfile(filename):
        with open(filename) as f:
            logger.debug(f'reading config file: {filename}')
            return yaml.safe_load(f.read())
    else:
        logger.error(f'failed to read config file: {filename}')
        return {}

def update_operating_database(device, running, startup, database):
    result = running and startup
    cursor = connect_to_db(database)

    if result:
        message = f'successfully backed up running and startup config for {device}'
        sql = """INSERT INTO device_backups (device, last_attempt, last_success, message) VALUES(%s, now(), now(), %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, last_success, message) = (now(), now(), EXCLUDED.message)"""
        cursor.execute(sql, (device, message))
    else:
        message = f'failed to backup running and/or startup config for {device} - {running} - {startup}'
        sql = """INSERT INTO device_backups (device, last_attempt, message) VALUES(%s, now(), %s)
                 ON CONFLICT (device) DO UPDATE SET 
                 (last_attempt, message) = (now(), EXCLUDED.message)"""
        cursor.execute(sql, (device, message))

    # commit data
    cursor.connection.commit()
    cursor.close()

def connect_to_db(database):
    conn = psycopg2.connect(
        host=database['host'],
        database=database.get('database', 'operating'),
        user=database['user'],
        password=database['password'],
        port=database.get('port', 5432)
    )

    cursor = conn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)
    return cursor

