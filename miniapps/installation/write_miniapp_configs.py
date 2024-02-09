#!/usr/bin/env python

import os
import sys
import argparse
import yaml
import shutil
from benedict import benedict


miniapps = ['onboarding','kobold','script_bakery','scan_prefixes',
            'check_and_set', 'check_inventory',
            'sync_cmk','sync_phpipam','sync_smokeping','dispatcher',
            'nachtwaechter', 'library_importer']
profiles = ['onboarding','kobold','script_bakery', 'nachtwaechter']
additional = {}
copy_files = {'nachtwaechter': ['index.yaml','mapping.conf.example']}

BASEDIR = os.path.abspath('')
HOMEDIR = os.path.expanduser('~')

veritas_config_basepath = f'{HOMEDIR}/.veritas/miniapps/'

def replace_placeholders(app, app_config, config):
    app_config = app_config.replace('__username__', config['profile']['username'])
    app_config = app_config.replace('__password__', config['profile']['password'])
    
    # app specific config
    if app in config:
        flatten_config = config[app].flatten(separator="_")
        for key, value in flatten_config.items():
            if isinstance(value, str) and '{HOMEDIR}' in value:
                value = value.replace("{HOMEDIR}", HOMEDIR)
            app_config = app_config.replace(f'__{key}__', str(value))
        
    flatten_config = config.flatten(separator="_")
    for key, value in flatten_config.items():
        if isinstance(value, str) and '{HOMEDIR}' in value:
            value = value.replace("{HOMEDIR}", HOMEDIR)
        app_config = app_config.replace(f'__{key}__', str(value))

    return app_config

def main_loop(config, app, filename, veritas_config_basepath):
    config_filename = f'{veritas_config_basepath}/{app}/{filename}.yaml'
    directory = os.path.dirname(config_filename)
    if not os.path.exists(directory):
        os.makedirs(directory)
    app_example_config = f'{BASEDIR}/../{app}/conf/{filename}.yaml.example'
    if os.path.isfile(app_example_config):
        with open(app_example_config, "r") as f:
            app_config = f.read()
        new_config = replace_placeholders(app, app_config, config)
        with open(config_filename, "w") as f:
            f.write(new_config)
    else:
        print(f'config {app_example_config} does not exist')

def main():
    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--config-values', type=str, default='config_values.yaml', help='read config values')
    parser.add_argument('--basepath', type=str, default=f'{HOMEDIR}/.veritas/miniapps/', help='basepath')

    # parse arguments
    args = parser.parse_args()

    with open(args.config_values) as f:
        try:
            cfg = yaml.safe_load(f.read())
        except Exception as exc:
            print(f'could not read or parse config {exc}')
            sys.exit()

    veritas_config_basepath = args.basepath
    config = benedict(cfg, keyattr_dynamic=True)

    for app in miniapps:
        main_loop(config, app, app, veritas_config_basepath)
    for app in profiles:
        main_loop(config, app, 'profiles', veritas_config_basepath)
        main_loop(config, app, 'salt', veritas_config_basepath)
    for app in additional:
        main_loop(config, app, additional[app], veritas_config_basepath)

    for app in copy_files:
        for filename in copy_files[app]:
            soure = f'{BASEDIR}/../{app}/conf/{filename}'
            destination = f'{veritas_config_basepath}/{app}/{filename}'
            shutil.copy(soure, destination, follow_symlinks=True)

if __name__ == "__main__":
    main()