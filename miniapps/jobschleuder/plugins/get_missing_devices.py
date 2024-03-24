from loguru import logger
import yaml

# veritas
from veritas.sot import sot as veritas_sot
from veritas.plugin import jobschleuder
import database_handling


@jobschleuder("get_missing_devices")
def get_missing_devices(*args, **kwargs):
    # list of jobs to do
    jobs = []
    # the list of all nautobot devices
    all_devices = []
    # the list of backuped devices
    backuped_devices = {}

    # read config
    filename = './conf/get_missing_devices.yaml'
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

    # open database connection
    cursor = database_handling.connect_to_db(local_config_file.get('database'))

    # get list of ALL backups
    sql = """SELECT device FROM device_backups"""
    try:
        cursor.execute(sql, )
        db_devices = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from database {exc}')
        return []
    
    for device in db_devices:
        backuped_devices[device['device']] = True

    # get all devices from nautobot
    limit = kwargs.get('limit', 500)
    offset = 0

    while True:
        devices = sot.select('name, platform, primary_ip4') \
                         .using('nb.devices') \
                         .set(limit=limit, offset=offset) \
                         .where()
        if len(devices) == 0:
            break
        logger.bind(extra="preproc").debug(f'got {len(devices)} devices')
        all_devices = all_devices + devices
        offset += len(devices)
    
    for device in all_devices:
        name = device.get('name')
        primary_ip4 = device.get('primary_ip4',{}).get('address')

        # we need the primary_ip4 to connect to the device
        if not primary_ip4:
            logger.error(f'no primary_ip4 for device {name}')
            continue
        else:
            primary_ip4 = primary_ip4.split('/')[0]

        if name not in backuped_devices:
            logger.info(f'backup missing for device {name}')
            jobs.append(
            {'cmd': 'simple_config_backup', 'args': 
                {'name': name, 
                 'platform': device.get('platform',{}).get('name'),
                 'primary_ip4': primary_ip4
                }
            }
        )

    return jobs
