from loguru import logger
import re

# veritas
from veritas.plugin import jobschleuder


@jobschleuder("preprocessing_backup")
def expand_devices(*args, **kwargs):
    jobs = []
    sot = kwargs['sot']
    where = kwargs['where']
    exclude = kwargs.get('exclude', [])
    excluded_pattern = exclude.get('pattern', None)

    # get the list of devices from our sot
    device_list = sot.select('name, platform, primary_ip4') \
                     .using('nb.devices') \
                     .where(where)

    for device in device_list:
        name = device.get('name')
        # check if the device is in the exclude list
        if name in exclude.get('devices', []):
            logger.info(f'skipping device {name} as it is in the exclude list')
            continue
        # check the list of pattern to exclude
        if excluded_pattern:
            pattern_matched = False
            for pattern in excluded_pattern:
                if re.match(pattern, name):
                    logger.info(f'skipping device {name} as it matches the exclude pattern {pattern}')
                    pattern_matched = True
            if pattern_matched:
                continue
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
