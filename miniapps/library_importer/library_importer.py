#!/usr/bin/env python

import argparse
import yaml
import sys
import glob
import os
import urllib3
from loguru import logger

import veritas.logging
import veritas.repo
from veritas.sot import sot as veritas_sot
from veritas.tools import tools

#
# The device library comes from netbox
#

def read_and_convert_data(sot, config, name):
    repo = config['files'][name]['repo']
    path = config['files'][name]['path']
    filename = config['files'][name]['filename']
    logger.debug(f'getting {name} from repo {repo}/{filename}')
    repo = veritas.repo.Repository(repo=repo, path=path)

    if '.xlsx' in filename:
        data = {name: []}
        flnm = f'{path}/{filename}'
        logger.debug(f'reading {flnm}')
        table = tools.read_excel_file(flnm)
        for row in table:
            d = {}
            for key,value in row.items():
                if value:
                    logger.debug(f'key: {key} value: {value}')
                    tools.set_value(d, key, value)
            data[name].append(d)
        logger.debug(f'data: {data}')
        return data
    else:
        # read yaml file from repo
        items = repo.get(filename)
        try:
            return yaml.safe_load(items)
        except Exception as exc:
            logger.error(f'could no convert items to yaml; {exc}')
            return None

def import_data(sot, config, args):
    # the device library comes from netbox
    if args.device_library:
        directory = args.device_library
        logger.debug(f'reading device_type library from {directory}')
        for filename in glob.glob(os.path.join(directory, "*.yaml")):
            logger.debug(f'found file {filename}')
            with open(filename) as f:
                logger.debug(f'reading {filename}')
                try:
                    content = yaml.safe_load(f.read())
                except Exception as exc:
                    logger.error("could not read file %s; got exception %s" %
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
                device_type_added = sot.importer.add(properties=device_types, endpoint='device_types')
                if device_type_added and 'interfaces' in content:
                    data = []
                    for interface in content['interfaces']:
                        interface.update({'device_type': {'model': content.get('model')}})
                        data.append(interface)
                    success = sot.importer.add(properties=data, endpoint='interface_templates', bulk=True)
                if device_type_added and 'console-ports' in content:
                    data = []
                    for console in content['console-ports']:
                        console.update({'device_type': {'model': content.get('model')}})
                        data.append(console)
                    success = sot.importer.add(properties=data, endpoint='console_port_templates', bulk=True)
                if device_type_added and 'power-ports' in content:
                    data = []
                    for power in content['power-ports']:
                        power.update({'device_type': {'model': content.get('model')}})
                        data.append(power)
                    success = sot.importer.add(properties=data, endpoint='power_port_templates', bulk=True)
                if device_type_added and 'module-bays' in content:
                    data = []
                    for module in content['module-bays']:
                        module.update({'device_type': {'model': content.get('model')}})
                        data.append(module)
                    success = sot.importer.add(properties=data, endpoint='device_bay_templates', bulk=True)
                    if success:
                        logger.info('device library successfully imported')


if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, required=False)
    # what to import
    parser.add_argument('--device-library', type=str, help='directory of device library')

    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    parser.add_argument('--debug-veritas', action='store_true', help='enable veritas debug logging')

    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    config = tools.get_miniapp_config('library_importer', BASEDIR, args.config)
    if not config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='library_importer',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=config['sot']['token'], 
                          url=config['sot']['nautobot'],
                          ssl_verify=config['sot']['ssl_verify'],
                          debug=args.debug_veritas)

    import_data(sot, config, args)
