import re
import yaml
import os
import glob
import json
from loguru import logger
from veritas.sot import sot as sot


def required(sot, args, device_fqdn, device_defaults, device_facts, ciscoconf):
    cfields = from_file(sot, args, device_fqdn, device_defaults, device_facts, ciscoconf, True)
    print(cfields)

def to_sot(sot, args, device_fqdn, device_defaults, device_facts, ciscoconf):

    hldm = []

    cli_fields = from_default_and_cli(sot, args, device_fqdn, device_defaults)
    file_fields = from_file(sot, args, device_fqdn, device_defaults, device_facts, ciscoconf)

    if cli_fields:
        for cfield in cli_fields:
            hldm.append(cfield)
    if file_fields:
        for cfield in file_fields:
            hldm.append(cfield)

    return hldm

def from_default_and_cli(sot, args, device_fqdn, device_defaults):
    logger.debug(f'adding custom fields from default values and cli')

    response = []

    if args.add_custom_fields:
        for cfield in args.add_custom_fields.split(','):
            if args.write_hldm or args.show_hldm:
                response.append({'name': cfield, 'scope': 'dcim.device'})
            else:
                add_custom_field_to_sot(sot, args, cfield, 'dcim.device', device_fqdn, None)

    if 'custom_fields' in device_defaults:
        for cfield in device_defaults['custom_fields'].split(','):
            if args.write_hldm or args.show_hldm:
                response.append(property = {'name': cfield, 'scope': 'dcim.device'})
            else:
                add_custom_field_to_sot(sot, args, cfield, 'dcim.device', device_fqdn, None)

    return response

def from_device_properties(device_fqdn, device_facts, host_or_ip, config):
    logger.debug(f'adding device custom fields depending on hostname or ip')
    response = []

    if isinstance(host_or_ip, dict):
        list_of_items.append(host_or_ip)
    else:
        list_of_items = host_or_ip

    for item in list_of_items:
        custom_field = item.get('custom_field')
        value = item.get('value')
        del item['custom_field']
        del item['value']
        for p_name, p_value in item.items():
            if '__' in p_name:
                splits = p_name.split('__')
                key = splits[0]
                expression = splits[1]
                if 're' == expression:
                    logger.debug(f'regular expression {p_value} found')
                    

    return response

def read_file(filename, device_defaults, required):
    with open(filename) as f:
        config = {}
        logger.debug("opening file %s to read custom field config" % filename)
        try:
            config = yaml.safe_load(f.read())
            if config is None:
                logger.error("could not parse file %s" % filename)
                return None
        except Exception as exc:
            logger.error("could not read file %s; got exception %s" % (filename, exc))
            return None
        name = config.get('name')
        platform = config.get('platform')

        if not config.get('active'):
            logger.debug("tags %s in %s is not active" % (name, filename))
            return None
        if platform is not None:
            if platform != 'all' and platform != device_defaults.get("platform",''):
                logger.debug("skipping custom field %s wrong platform %s" % (name, platform))
                return None
        if required and not config.get('required', False):
            # this file contains required custom fields
            logger.debug('this file is not required but required is set to True')
            return None

        return config

def from_file(sot, args, device_fqdn, device_defaults, device_facts, ciscoconf, required=False):

    basedir = "%s/%s" % (onboarding_config.get('git').get('app_configs').get('path'),
                         onboarding_config.get('git').get('app_configs').get('subdir'))
    directory = os.path.join(basedir, './custom_fields/')
    files = []
    cfields = []

    # we read all *.yaml files in our cusrom field config dir
    for filename in glob.glob(os.path.join(directory, "*.yaml")):
        config = read_file(filename, device_defaults, required)
        if config is None:
            continue

        # add filename to our list of files that were processed
        files.append(os.path.basename(filename))

        # get the source. It is either a section or a (named) regular expression
        if 'section' in config['source']:
            device_config = ciscoconf.get_section(config['source']['section'])
            cfields = parse_config(device_config, config)
        elif 'fullconfig' in config['source']:
            device_config = ciscoconf.get_device_config().splitlines()
            cfields = parse_config(device_config, config)
        elif 'device' in config['source']:
            cfields = from_device_properties(device_fqdn, device_facts, config['source']['device'], config)
        else:
            logger.error("unknown source %s" % config['source'])
            continue

        if required:
            return cfields

        for cfield in cfields:
            print(cfield)

def parse_config(device_config, config):
    response = []

    for cfield in config.get('custom_fields',[]):
        pattern = cfield.get('pattern', None)
        contains = cfield.get('contains', None)
        scope_of_cfield = cfield.get('scope', 'dcim.device')
        name_of_cfield = cfield.get('name')
        if pattern:
            logger.debug(f'name: {name_of_cfield} scope: {scope_of_cfield} pattern: {pattern}')
            compiled = re.compile(pattern)
        elif contains:
            logger.debug(f'name: {name_of_cfield} scope: {scope_of_cfield} string: {contains}')
        interface = None
        for line in device_config:
            # check if we havew an interface that is needed with scope dcim.interface
            if line.lower().startswith('interface '):
                interface = line[10:]
            if pattern:
                match = compiled.match(line)
                if match:
                    logger.debug(f'pattern found on interface {interface}')
                    if scope_of_cfield == "dcim.interface" and interface is not None:
                        response.append({'name': name_of_cfield, 
                                         'scope': scope_of_cfield, 
                                         'interface': interface})
                    elif scope_of_cfield == "dcim.device":
                        response.append({'name': name_of_cfield, 
                                         'scope': scope_of_cfield, 
                                         'interface': interface})
            elif contains and contains in line:
                logger.debug(f'string found on interface {interface}')
                if scope_of_cfield == "dcim.interface" and interface is not None:
                    response.append({'name': name_of_cfield, 
                                     'scope': scope_of_cfield, 
                                     'interface': interface})
                elif scope_of_cfield == "dcim.device":
                    response.append({'name': name_of_cfield, 
                                     'scope': scope_of_cfield, 
                                     'interface': interface})
    
    return response

def add_custom_field_to_sot(sot, args, name_of_cfield, scope_of_cfield, device_fqdn, key):
    logger.info(f'adding custom field {name_of_cfield} to {device_fqdn}')
    for scope in scope_of_cfield.split(","):
        if key is not None and scope == "dcim.interface":
            response = sot.device(device_fqdn).interface(key).add_custom_field(name_of_cfield)
            if response:
                logger.info(f'custom fields added to interface')

        if scope == "dcim.device":
            response = sot.device(device_fqdn).add_custom_field(name_of_cfield)
            if response:
                logger.info(f'tags added to device')
