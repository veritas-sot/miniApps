import json
import sys
from datetime import datetime
from slugify import slugify
from veritas.sot import sot
from businesslogic import your_device as user_bc_device
from onboarding import additional as additional


def get_device_properties(sot, device_fqdn, device_facts, ciscoconf, device_properties, onboarding_config):
    # if the device model was set in device_facts we use this value instead of the default value
    device_properties['device_type'] = device_facts.get('device_type', device_facts.get('model'))

    # check if serial_number is list or string. We need {'12345','12345'}
    if isinstance(device_facts["serial_number"], list):
        sn = ', '.join(map(str, device_facts["serial_number"]))
    else:
        sn = device_facts["serial_number"]

    # set custom fields; slugify value
    cf_fields = {}
    for key, value in device_properties.get('custom_fields',{}).items():
        if value is not None:
            cf_fields[key.lower()] = slugify(value)

    # slugify device_type
    if 'device_type' in device_properties:
        device_properties['device_type'] = slugify(device_properties['device_type'])

    # set current time
    now = datetime.now()
    current_time = now.strftime('%Y-%m-%d %H:%M:%S')
    cf_fields.update({'last_modified': current_time})

    try:
        # add tags if tags are not None
        device_tags = device_properties.get('tags', None)
        if device_tags is not None:
            device_properties.update({'tags': device_tags})

        # add user defined additional values
        additional_values = additional.additional(device_properties,
                                                  device_facts,
                                                  ciscoconf,
                                                  onboarding_config)

        # merge the device properties and the additional values
        for key,value in additional_values.items():
            logger.debug(f'updating device_properties with {key}={value}')
            if key == 'primary_ip' and len(value) > 0:
                primary_address = value
                primary_interface_name = ciscoconf.get_interface_name_by_address(primary_address)
                new_primary_interface = ciscoconf.get_interface(primary_interface_name)
                # we need the name of the interface
                if 'name' not in new_primary_interface:
                    new_primary_interface['name'] = primary_interface_name
                if new_primary_interface:
                    logger.info(f'change primary_ip to {primary_address} and interface {primary_interface_name}')
                    device_properties['primary_interface'] = new_primary_interface
            elif key in ['manufacturer', 'role'] and len(value) > 0:
                # manufacturer and platform need the name
                if isinstance(value, dict):
                    device_properties[key] = value
                else:    
                    device_properties[key] = {'name': slugify(value)}
            elif key in ['device_type'] and len(value) > 0:
                device_properties[key] = {'model': slugify(value)}
            elif key in ['platform'] and len(value) > 0:
                # device_type is simple
                device_properties[key] = value
            elif key in ['location'] and len(value) > 0:
                if isinstance(value, dict):
                    device_properties[key] = value
                else:    
                    device_properties[key] = {key: slugify(value)}
            elif key.startswith('cf_'):
                k = key.split('cf_')[1]
                cf_fields[k] = value
            else:
                device_properties[key] = value
        # add custom fields to device properties
        device_properties.update({'custom_fields': cf_fields})
    except Exception as exc:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        logger.error("setting device properties failed in line %s; got: %s (%s, %s, %s)" % (exc_tb.tb_lineno,
                                                                                             exc,
                                                                                             exc_type,
                                                                                             exc_obj,
                                                                                             exc_tb))
        logger.error(f'device_properties: {device_properties}')
        return

    # call the user defined business logic
    # the business logic can be used to modify the data that is onboarded
    logger.debug("calling (pre processing) business logic of device %s to sot" % device_fqdn)
    user_bc_device.device_pre_processing(sot, device_properties, device_properties, ciscoconf, onboarding_config)

    return device_properties

def backup_config(sot, device_fqdn, raw_device_config, onboarding_config):
    logger.info("write backup config")

    subdir = ""
    name_of_repo = onboarding_config['git']['backup']['repo']
    path_to_repo = onboarding_config['git']['backup']['path']
    subdir = onboarding_config['git']['backup']['subdir']

    backup_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
    filenane = "%s/%s.conf" %(subdir, device_fqdn)
    backup_repo.write(filename, raw_device_config)
