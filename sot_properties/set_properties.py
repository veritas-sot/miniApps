#!/usr/bin/env python

import argparse
import json
import yaml
import sys
import logging
import glob
import os
from veritas.sot import sot as sot
from veritas.tools import tools

# set default config file to your needs
default_config_file = "./config.yaml"

def read_and_convert_data(sot, config, name):
    repo = config['files'][name]['repo']
    path = config['files'][name]['path']
    filename = config['files'][name]['filename']
    logging.debug(f'getting {name} from repo {repo}/{filename}')
    repo = sot.repository(repo=repo, path=path)
    items = repo.get(filename)

    try:
        return yaml.safe_load(items)
    except Exception as exc:
        logging.error(f'could no convert items to yaml; {exc}')
        return None

def import_data(config, args):
    # we need the SOT object to talk to the SOT
    my_sot = sot.Sot(token=config['sot']['token'], 
                     url=config['sot']['nautobot'],
                     ssl_verify=config['sot']['ssl_verify'])

    # the location types
    if args.location_types or args.all:
        location_types = read_and_convert_data(my_sot, config, 'location_types')
        logging.debug(f'import location_types')
        success = my_sot.importer.add(properties=location_types['location_types'], endpoint='location_types')

    # the locations
    if args.locations or args.all:
        locations = read_and_convert_data(my_sot, config, 'locations')
        logging.debug(f'import locations')
        success = my_sot.importer.add(properties=locations['locations'], endpoint='locations')

    # now the manufacturers
    if args.manufacturers or args.all:
        manufacturers = read_and_convert_data(my_sot, config, 'manufacturers')
        logging.debug(f'import manufacturers')
        success = my_sot.importer.add(properties=manufacturers['manufacturers'], endpoint='manufacturers')

    # the platforms
    if args.platforms or args.all:
        platforms = read_and_convert_data(my_sot, config, 'platforms')
        logging.debug(f'import platforms')
        success = my_sot.importer.add(properties=platforms['platforms'], endpoint='platforms', bulk=True)

    # roles
    if args.roles or args.all:
        roles = read_and_convert_data(my_sot, config, 'roles')
        logging.debug(f'import roles')
        success = my_sot.importer.add(properties=roles['roles'], endpoint='roles')

    # the prefixe
    if args.prefixes or args.all:
        prefixes = read_and_convert_data(my_sot, config, 'prefixes')
        logging.debug(f'import prefixes')
        success = my_sot.importer.add(properties=prefixes['prefixes'], endpoint='prefixes', bulk=True)

    # the device types
    if args.device_types or args.all:
        device_types = read_and_convert_data(my_sot, config, 'device_types')
        logging.debug(f'import device_types')
        success = my_sot.importer.add(properties=device_types['device_types'], endpoint='device_types')

    # the device library comes from netbox
    if args.device_library:
        directory = config['device_library'].get('directory')
        logging.debug(f'reading device_type library from {directory}')
        for filename in glob.glob(os.path.join(directory, "*.yaml")):
            with open(filename) as f:
                logging.debug(f'reading {filename}')
                try:
                    content = yaml.safe_load(f.read())
                except Exception as exc:
                    logging.error("could not read file %s; got exception %s" %
                                (filename, exc))
                    continue
                device_types = [{
                    'name': content.get('slug'),
                    'model': content.get('model'),
                    'manufacturer': {'name': content.get('manufacturer')},
                    'part_number': content.get('part_number'),
                    'u_height': content.get('u_height'),
                    'is_full_depth': content.get('is_full_depth')}]
                # if there is a module bay we set subdevice_role to parent
                if 'comments' in content:
                     device_types[0].update({'comments': content.get('comments')})
                if 'module-bays' in content:
                    device_types[0].update({'subdevice_role': 'parent'})
                device_type_added = my_sot.importer.add(properties=device_types, endpoint='device_types')
                if device_type_added and 'interfaces' in content:
                    data = []
                    for interface in content['interfaces']:
                        interface.update({'device_type': {'name': content.get('slug')}})
                        data.append(interface)
                    success = my_sot.importer.add(properties=data, endpoint='interface_templates', bulk=True)
                if device_type_added and 'console-ports' in content:
                    data = []
                    for console in content['console-ports']:
                        console.update({'device_type': {'name': content.get('slug')}})
                        data.append(console)
                    success = my_sot.importer.add(properties=data, endpoint='console_port_templates', bulk=True)
                if device_type_added and 'power-ports' in content:
                    data = []
                    for power in content['power-ports']:
                        power.update({'device_type': {'name': content.get('slug')}})
                        data.append(power)
                    success = my_sot.importer.add(properties=data, endpoint='power_port_templates', bulk=True)
                if device_type_added and 'module-bays' in content:
                    data = []
                    for module in content['module-bays']:
                        module.update({'device_type': {'name': content.get('slug')}})
                        data.append(module)
                    success = my_sot.importer.add(properties=data, endpoint='device_bay_templates', bulk=True)

    # read country library
    if args.country_library:
        filename = config['country_library'].get('directory')
        logging.debug(f'reading country library {filename}')
        raw_countries = []
        with open(filename) as f:
            try:
                raw_countries = json.load(f)
            except:
                logging.error(f'could not read country library {filename}')
        countries = []
        for country in raw_countries:
            country = {'name': country.get('country'),
                       'location_type': {'name': 'country'},
                       'status': 'active',
                       'site': {'name': 'default-site'}}
            countries.append(country)
        logging.debug('now adding countries')
        success = my_sot.importer.locations(properties=countries, bulk=True)

    # the tags
    if args.tags or args.all:
        locations = read_and_convert_data(my_sot, config, 'tags')
        logging.debug(f'import tags')
        success = my_sot.importer.add(properties=locations['tags'], endpoint='tags')

    # the custom fields
    if args.custom_fields or args.all:
        set_defaults = []
        custom_fields = read_and_convert_data(my_sot, config, 'custom_fields')
        custom_field_choices = read_and_convert_data(my_sot, config, 'custom_field_choices')
        for cf in custom_fields['custom_fields']:
            logging.debug(f'importing {cf}')
            if 'default' in cf:
                logging.debug('found default value; setting default after creating cf')
                properties = {'label': cf.get('label'), 'default': cf.get('default')}
                set_defaults.append(properties)
                del cf['default']
        logging.debug(f'import custom fields')
        success = my_sot.importer.add(properties=custom_fields['custom_fields'], endpoint='custom_fields')
        logging.debug(f'import custom fields choices')
        success = my_sot.importer.add(properties=custom_fields['custom_field_choices'], endpoint='custom_field_choices')
        # set default value
        for properties in set_defaults:
            success = my_sot.updater.update(endpoint='custom_fields', getter={'label': properties.get('label')}, values=properties)

    if args.custom_links or args.all:
        locations = read_and_convert_data(my_sot, config, 'custom_links')
        logging.debug(f'import custom links')
        success = my_sot.importer.add(properties=locations['custom_links'], endpoint='custom_links')

    # the webhooks
    if args.webhooks or args.all:
        locations = read_and_convert_data(my_sot, config, 'webhooks')
        logging.debug(f'import webhooks')
        success = my_sot.importer.add(properties=locations['webhooks'], endpoint='webhooks')

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False)
    # what to import
    parser.add_argument('--all', help='import all values', action='store_true')
    parser.add_argument('--manufacturers', help='import manuifacturers', action='store_true')
    parser.add_argument('--platforms', help='import platforms', action='store_true')
    parser.add_argument('--prefixes', help='import prefixes', action='store_true')
    parser.add_argument('--roles', help='import roles', action='store_true')
    parser.add_argument('--device-types', help='import device types', action='store_true')
    parser.add_argument('--location-types', help='import location types', action='store_true')
    parser.add_argument('--locations', help='import locations', action='store_true')
    parser.add_argument('--tags', help='import tags', action='store_true')
    parser.add_argument('--custom-fields', help='import custom fields', action='store_true')
    parser.add_argument('--custom-links', help='import custom links', action='store_true')
    parser.add_argument('--webhooks', help='import tags', action='store_true')
    parser.add_argument('--device-library', help='import library', action='store_true')
    parser.add_argument('--country-library', help='import countries', action='store_true')

    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="onboarding loglevel")

    args = parser.parse_args()

    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file        

    with open(config_file) as f:
        config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(config, ['logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(config, ['logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(config, ['logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)#, filename=logfile)

    import_data(config, args)
