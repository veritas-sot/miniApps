from loguru import logger
import re
import os
import yaml

# veritas
from veritas.sot import sot as veritas_sot
from veritas.plugin import jobschleuder
from veritas.tools import tools
import database_handling


@jobschleuder("get_failed_backups")
def retry_failed_backups(*args, **kwargs):

    # list of jobs to do
    jobs = []

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    filename = './conf/get_failed_backups.yaml'
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
    conn, cursor = database_handling.connect_to_db(local_config_file.get('database'))

    # get list of failed backups
    sql = """SELECT device FROM device_backups WHERE status = false"""
    try:
        cursor.execute(sql, )
        failed_devices = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from journals {exc}')
        return []

    device_list = []
    for failed_device in failed_devices:
        name = failed_device['device']
        device = sot.select('name, platform, primary_ip4') \
                        .using('nb.devices') \
                        .where(f'name={name}')
        device_list.append(device[0])

    for device in device_list:
        name = device.get('name')
        primary_ip4 = device.get('primary_ip4',{}).get('address')

        # we need the primary_ip4 to connect to the device
        if not primary_ip4:
            logger.error(f'no primary_ip4 for device {device.get("name")}')
            continue
        else:
            primary_ip4 = primary_ip4.split('/')[0]
        
        # add the job
        jobs.append(
            {'cmd': 'simple_config_backup', 'args': 
                {'name': name, 
                 'platform': device.get('platform',{}).get('name'),
                 'primary_ip4': primary_ip4
                }
            }
        )
    return jobs
