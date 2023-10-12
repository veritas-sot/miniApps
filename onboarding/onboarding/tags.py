import re
import yaml
import logging
import os
import glob
import json
from veritas.sot import sot as sot


def to_sot(sot, args, device_fqdn, device_defaults, device_facts, configparser):

    tags = []

    cli_tags = from_default(sot, args, device_fqdn, device_defaults)
    file_tags = from_file(sot, args, device_fqdn, device_defaults, device_facts, configparser)

    if cli_tags:
        for tag in cli_tags:
            tags.append(tag)
    if file_tags:
        for tag in file_tags:
            tags.append(tag)

    return tags

def from_default(sot, args, device_fqdn, device_defaults):
    logging.debug(f'adding tags from default values')

    response = []

    if 'tag' in device_defaults:
        for tag in device_defaults['tag'].split(','):
            response.append(property = {'name': tag, 'scope': 'dcim.device'})

    return response

def from_device_properties(sot, args, device_fqdn, device_facts, host_or_ip, config):
    logging.debug(f'adding device tags depending on hostname or ip')

    list_of_items = []
    list_of_ip = []
    list_of_hostnames = []
    list_of_models = []
    list_of_manufacturers = []
    list_of_os_version = []

    if isinstance(host_or_ip, dict):
        list_of_items.append(host_or_ip)
    else:
        list_of_items = host_or_ip

    for item in list_of_items:
        if 'ip' in item:
            list_of_ip.append(item['ip'])
        if 'hostname' in item:
            list_of_hostnames.append(item['hostname'])
        if 'model' in item:
            list_of_models.append(item['model'])
        if 'manufacturer' in item:
            list_of_manufacturers.append(item['manufacturer'])
        if 'os_version' in item:
            list_of_os_version.append(item['os_version'])

    if device_fqdn in list_of_hostnames or device_facts['args.device'] in list_of_ip or \
       device_facts['model'] in list_of_models or device_facts['manufacturer'] in list_of_manufacturers or \
       device_facts['os_version'] in list_of_os_version:
        if 'tags' in config:
            for tag in config['tags']:
                property = {'name': tag['name'],
                            'scope': 'dcim.device'}
                add_tag_to_sot(sot, args, property, device_fqdn, None)

def read_file(filename, device_defaults):
    with open(filename) as f:
        config = {}
        logging.debug("opening file %s to read custom field config" % filename)
        try:
            config = yaml.safe_load(f.read())
            if config is None:
                logging.error("could not parse file %s" % filename)
                return None
        except Exception as exc:
            logging.error("could not read file %s; got exception %s" % (filename, exc))
            return None

        name = config.get('name')
        platform = config.get('platform')
        if not config.get('active'):
            logging.debug("tags %s in %s is not active" % (name, filename))
            return None
        if platform is not None:
            if platform != 'all' and platform != device_defaults["platform"]:
                logging.debug("skipping custom field %s wrong platform %s" % (name, platform))
                return None
        return config

def from_file(sot, args, device_fqdn, device_defaults, device_facts, configparser):

    response = None

    basedir = "%s/%s" % (onboarding_config.get('git').get('app_configs').get('path'),
                         onboarding_config.get('git').get('app_configs').get('subdir'))
    directory = os.path.join(basedir, './tags/')

    # we read all *.yaml files in our tags config dir
    for filename in glob.glob(os.path.join(directory, "*.yaml")):
        config = read_file(filename, device_defaults)
        if config is None:
            continue

        # get the source. It is either a section or a (named) regular expression
        if 'section' in config['source']:
            device_config = configparser.get_section(config['source']['section'])
        elif 'fullconfig' in config['source']:
            device_config = configparser.get_device_config().splitlines()
        elif 'device' in config['source']:
            # TODO die tags werden zentral zur SOT hinzugefügt
            from_device_properties(sot, args, device_fqdn, device_facts, config['source']['device'], config)
            continue
        else:
            logging.error("unknown source %s" % config['source'])
            continue

        if len(device_config) == 0:
            logging.error("no device config with configured pattern found")
            continue

        # print(json.dumps(device_config, indent=4))
        parse_config(sot, args, device_config, device_fqdn, config)

    return response

def parse_config(sot, args, device_config, device_fqdn, config):
    for tags in config.get('tags',[]):
        pattern = tags.get('pattern', None)
        contains = tags.get('contains', None)
        scope_of_tag = tags.get('scope', 'dcim.device')
        name_of_tag = tags.get('name')
        if pattern:
            logging.debug(f'name: {name_of_tag} scope: {scope_of_tag} pattern: {pattern}')
            compiled = re.compile(pattern)
        elif contains:
            logging.debug(f'name: {name_of_tag} scope: {scope_of_tag} string: {contains}')
        interface = None
        for line in device_config:
            # check if we have an interface that is needed with scope dcim.interface
            if line.lower().startswith('interface '):
                interface = line[10:]
            if pattern:
                match = compiled.match(line)
                if match:
                    logging.debug(f'pattern found on interface {interface}')
                    if scope_of_tag == "dcim.interface" and interface is not None:
                        add_tag_to_sot(sot, args, name_of_tag, scope_of_tag, device_fqdn, interface)
                    elif scope_of_tag == "dcim.device":
                        add_tag_to_sot(sot, args, name_of_tag, scope_of_tag, device_fqdn, None)
            elif contains and contains in line:
                logging.debug(f'string found on interface {interface}')
                if scope_of_tag == "dcim.interface" and interface is not None:
                    add_tag_to_sot(sot, args, name_of_tag, scope_of_tag, device_fqdn, interface)
                elif scope_of_tag == "dcim.device":
                    add_tag_to_sot(sot, args, name_of_tag, scope_of_tag, device_fqdn, None)

def add_tag_to_sot(sot, args, name_of_tag, scope_of_tag, device_fqdn, key):
    logging.info(f'adding tag {name_of_tag} to {device_fqdn}')
    for scope in scope_of_tag.split(","):
        if key is not None and scope == "dcim.interface":
            tag = sot.device(device_fqdn).interface(key).add_tags(name_of_tag)
            if tag:
                logging.info(f'tags added to interface')

        if scope == "dcim.device":
            tag = sot.device(device_fqdn).add_tags(name_of_tag)
            if tag:
                logging.info(f'tags added to device')
