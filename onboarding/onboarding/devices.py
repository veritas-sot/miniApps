import logging
import json
import sys
from datetime import datetime
from slugify import slugify
from veritas.sot import sot
from businesslogic import your_device as user_bc_device
from onboarding import required as required
from ipaddress import IPv4Network


def to_sot(sot, args, device_fqdn, device_facts, ciscoconf, primary_address, device_defaults, onboarding_config):
    # init some vars
    primary_interface_properties = {}
    device_defaults['device_type'] = device_facts['model']

    # set primary IP/Interface of device and check if the primary IP has the wrong format
    primary_interface_name = ciscoconf.get_interface_name_by_address(primary_address)
    # if primary_interface_name is none then the IP address was not configured on an interfcae
    # this can happen when using dhcp (strange but possible) or hsrp (more common)
    logging.debug(f'primary_interface_name set to {primary_interface_name}')
    primary_interface = ciscoconf.get_interface(primary_interface_name)

    # if we have the right mask of the interface/ip we use this instead of a /32
    if primary_interface is not None:
        # convert IP and MASK to cidr notation
        prefixlen = IPv4Network("0.0.0.0/%s" % primary_interface.get('mask')).prefixlen
        primary_address = "%s/%s" % (primary_interface.get('ip'), prefixlen)
        logging.debug(f'found primary interface; setting primary_address interface to {primary_address}')
        if primary_interface.get('description') == None:
            logging.info("primary interface has no description configured; using 'primary interface'")
            primary_interface['description'] = "primary interface"

    # check if serial_number is list or string. We need {'12345','12345'}
    if isinstance(device_facts["serial_number"], list):
        sn = ', '.join(map(str, device_facts["serial_number"]))
    else:
        sn = device_facts["serial_number"]

    # set custom fields; slugify value
    cf_fields = {}
    for key, value in device_defaults.get('custom_fields',{}).items():
        if value is not None:
            cf_fields[key.lower()] = slugify(value)

    # check tags
    device_tags = device_defaults.get('tags', None)

    # set current time
    now = datetime.now()
    current_time = now.strftime('%Y-%m-%d %H:%M:%S')
    cf_fields.update({'last_modified': current_time})

    # nautobot version 2 does not have any slug anymore
    # use name instead
    if args.version == 2:
        key = 'name'
    else:
        key = 'slug'

    try:
        device_properties = {
                "name": device_fqdn,
                #"device_type": {key: slugify(device_defaults['device_type'])},
                "manufacturer": {key: slugify(device_defaults['manufacturer'])},
                "platform": {key: slugify(device_defaults['platform'])},
                "serial": sn,
            }

        if args.version == 2:
            device_properties.update({'status': {'name': 'Active'}})
            device_properties.update({'location': {'name': device_defaults['site']}})
            device_properties.update({'role': {'name': device_defaults['device_role']}})
            # todo!!!
            device_properties.update({'device_type': 'a3648f35-4b4e-443f-b7cf-551503ff2025'})
        else:
            device_properties.update({'status': device_defaults['status']})
            device_properties.update({'site': {'slug': slugify(device_defaults['site'])}})
            device_properties.update({"device_role": {'slug': slugify(device_defaults['device_role'])}})

        # add tags if it is not None
        if device_tags is not None:
            device_properties.update({'tags': device_tags})

        # get additional values
        # additional values are values that MUST exists; otherwise the device 
        # cannot be added to the sot. For example some custom fields may be required
        additional_values = required.required(sot, 
                                              device_defaults, 
                                              device_facts, 
                                              ciscoconf, 
                                              onboarding_config)

        # merge the device properties and the required values
        for key,value in additional_values.items():
            logging.debug(f'updating device_properties with {key}={value}')
            if key == 'primary_ip' and len(value) > 0:
                primary_address = value
                primary_interface_name = ciscoconf.get_interface_name_by_address(primary_address)
                new_primary_interface = ciscoconf.get_interface(primary_interface_name)
                if new_primary_interface:
                    logging.info(f'change primary primary_ip to {primary_address} and interface {primary_interface_name}')
                    primary_interface = new_primary_interface
                    if primary_interface.get('description') == None:
                        logging.info("primary interface has no description configured; using 'primary interface'")
                        primary_interface['description'] = "primary interface"
            elif key in ['site', 'device_role', 'device_type', 'manufacturer', 'platform'] and len(value) > 0:
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
        logging.error("setting device properties failed in line %s; got: %s (%s, %s, %s)" % (exc_tb.tb_lineno,
                                                                                             exc,
                                                                                             exc_type,
                                                                                             exc_obj,
                                                                                             exc_tb))
        logging.error(f'values: {device_defaults}')
        logging.error(f'device_properties: {device_properties}')
        return

    # call the user defined business logic
    # the business logic can be used to modify the data that is onboarded
    logging.debug("calling (pre processing) business logic of device %s to sot" % device_fqdn)
    user_bc_device.device_pre_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config)

    if primary_interface is not None:
        primary_interface_properties = {'device': {'name': device_fqdn},
                                        'name': primary_interface_name,
                                        'description': primary_interface.get('description'),
                                        'type': primary_interface.get('type', '1000base-t')}

        if args.version == 2:
            primary_interface_properties.update({'status': {'name': 'Active'}})
        else:
            primary_interface_properties.update({'status': device_defaults['status']})

    if args.write_hldm or args.show_hldm:
        user_bc_device.device_post_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config)
        primary_interface_properties.update({'ip': primary_address})
        device_properties.update({'primary_interface': primary_interface_properties})
        return device_properties

    if not device_facts.get('is_in_sot', False):
        if primary_interface is not None:
            logging.info(f'adding device {device_fqdn} and primary interface to sot')
            logging.debug(f'primary_interface {primary_interface_properties} primary_ipv4 {primary_address}')
            sot.device(device_fqdn) \
                .use_defaults(True) \
                .return_device(True) \
                .primary_interface(primary_interface_properties) \
                .primary_ipv4(primary_address) \
                .make_primary(True) \
                .add(device_properties)
        else:
            logging.info(f'adding device {device_fqdn} without primary interface to sot')
            sot.device(device_fqdn).add(device_properties)
    else:
        logging.info(f'updating device {device_fqdn} in sot')
        sot.device(device_fqdn).update(device_properties)

    # call the user defined business logic
    # the user defined bl can overwrite and modify the device_context
    logging.debug("calling (post processing) business logic of device %s to sot" % device_fqdn)
    user_bc_device.device_post_processing(sot, device_properties, device_defaults, ciscoconf, onboarding_config)
    return {}

def backup_config(sot, device_fqdn, raw_device_config, onboarding_config):
    logging.info("write backup config")

    subdir = ""
    name_of_repo = args.repo or onboarding_config['git']['backup']['repo']
    path_to_repo = args.path or onboarding_config['git']['backup']['path']
    if args.subdir:
        subdir = args.subdir
    elif 'subdir' in  onboarding_config['git']['backup']:
        subdir = onboarding_config['git']['backup']['subdir']

    backup_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
    filenane = "%s/%s.conf" %(subdir, device_fqdn)
    backup_repo.write(filename, raw_device_config)
