#!/usr/bin/env python

import argparse
import os
import difflib
from dotenv import load_dotenv

# logging
from loguru import logger
# colorful output of the diff
from colorama import Fore
# our veritas lib
import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools
from veritas.devicemanagement import scrapli as dm


def get_configs(hostname, directory, live=False, ip=None, 
                username=None, password=None, platform='ios', manufacturer='cisco', port=22, 
                scrapli_loglevel='none'):

    if live:
        logger.bind(extra=hostname).debug('getting configs')
        conn = dm.Devicemanagement(ip="192.168.0.1",
                                   platform=platform,
                                   manufacturer=manufacturer,
                                   username=username,
                                   password=password,
                                   port=port,
                                   scrapli_loglevel=scrapli_loglevel)
        
        startup_config = conn.get_config('startup-config').splitlines()
        running_config = conn.get_config('running-config').splitlines()

    else:
        logger.bind(extra=hostname).debug('reading configs from file')
        running_filename = f'{directory}/{hostname}.running.cfg'
        startup_filename = f'{directory}/{hostname}.startup.cfg'
        with open(startup_filename, 'r') as sf:
            startup_config = [line.rstrip() for line in sf]
        with open(running_filename, 'r') as rf:
            running_config = [line.rstrip() for line in rf]

    return startup_config, running_config

def color_diff(diff):
    for line in diff:
        if line.startswith('+'):
            yield Fore.GREEN + line + Fore.RESET
        elif line.startswith('-'):
            yield Fore.RED + line + Fore.RESET
        elif line.startswith('^'):
            yield Fore.BLUE + line + Fore.RESET
        else:
            yield line

def main(args_list=None):

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="unique identifier")
    # output
    parser.add_argument('--output', type=str, default='text', required=False, help="output format")
    # get configs from device instead of checking local files
    parser.add_argument('--live', action='store_true', help='get configs from device')
    # what devices
    parser.add_argument('--devices', type=str, required=True, help="query to get list of devices")
    parser.add_argument('--config-dir', type=str, required=False, help="where to find the configs")
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False)
    parser.add_argument('--password', type=str, required=False)
    parser.add_argument('--profile', type=str, required=False)
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    local_config_file = tools.get_miniapp_config('script_bakery', BASEDIR, args.config)
    if not local_config_file:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='compare_configs',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=False)

    # if args.live is True we get the configs from the device
    if args.live:
        # check if .env file exists and read it
        if os.path.isfile(os.path.join(BASEDIR, '.env')):
            logger.debug('reading .env file')
            load_dotenv(os.path.join(BASEDIR, '.env'))
        else:
            logger.debug('no .env file found; trying to read local crypto parameter')
            crypt_parameter = tools.get_miniapp_config('script_bakery', BASEDIR, "salt.yaml")
            os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
            os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
            os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

        # load profiles
        profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')

        # get username and password either from profile
        username, password = tools.get_username_and_password(
            profile_config,
            args.profile,
            args.username,
            args.password)
    else:
        username = None
        password = None

    sot_devicelist = sot.select('name, primary_ip4, device_type, platform') \
                        .using('nb.devices') \
                        .where(args.devices)
    
    logger.debug(f'got {len(sot_devicelist)} device(s) from our SOT')

    config_dir = args.config_dir if args.config_dir else \
        local_config_file.get('backup',{}).get('backup_dir','./backups/')

    for device in sot_devicelist:
        hostname = device.get('name')
        primary_ip4 = device.get('primary_ip4',{})
        if not primary_ip4:
            logger.bind(extra=hostname).warning(f'no ip address for {hostname}')
            continue
        else:
            ip = primary_ip4.get('address').split('/')[0]
        if 'platform' in device and device['platform'] is None:
            logger.bind(extra=hostname).warning(f'no platform for {hostname}')
            continue
        platform = device.get('platform',{}).get('name')
        manufacturer = device.get('device_type',{}).get('manufacturer',{}).get('name','cisco')

        logger.bind(extra=hostname).debug(f'comparing configs of {hostname} ({ip}/{platform}/{manufacturer})')
        startup_config, running_config = get_configs(
                hostname=hostname,
                directory=f'{config_dir}/{hostname}/',
                live=args.live, 
                ip=ip, 
                username=username, 
                password=password, 
                platform=platform,
                manufacturer=manufacturer, 
                port=args.port)

        if args.live and manufacturer=='cisco':
            # cisco configs have some lines we do not need to compare the configs
            # cut off the first lines
            startup_config = startup_config[4:]
            running_config = running_config[7:]

        if args.output == 'html':
            html_diff = difflib.HtmlDiff()
            comparison_table = html_diff.make_file(startup_config, running_config)

            with open(f'{hostname}_diff.html', "w") as file:
                file.write(comparison_table)
        else:
            # we compare the startup config (baseline) with the running config
            diff = difflib.unified_diff(startup_config, running_config)
            if args.output == 'log':
                if len(list(diff)) == 0:
                    # the result is written to the database
                    result = {'app': 'compare_configs',
                              'details': {
                                'entity': hostname,
                                'message': 'no diff'}
                            }
                    logger.bind(result=result).journal(f'no diff found on {hostname}')
                else:
                    # the result is written to the database
                    result = {'app': 'compare_configs',
                              'details': {
                                'entity': hostname,
                                'message': 'running-config and startup-config differ'}
                             }
                    logger.bind(result=result).journal(f'configs differ on {hostname}')
            elif args.output == 'bool':
                if len(list(diff)) == 0:
                    print('no diff')
                else:
                    print('configs differ')
            else:
                diff = difflib.ndiff(startup_config, running_config)
                diff = color_diff(diff)
                print('\n'.join(diff))

if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../script_bakery')
    import compare_configs as cmp

    cmp.main(['--profile', 'default', 
              '--loglevel', 'debug',
              '--devices', 'name=lab.local'])


    """
    main()
