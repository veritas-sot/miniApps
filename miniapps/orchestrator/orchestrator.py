#!/usr/bin/env python

import argparse
import os
import sys
from loguru import logger
from dotenv import load_dotenv
from nornir_utils.plugins.functions import print_result

# veritas
import veritas.logging
import veritas.profile
from veritas.sot import sot as veritas_sot
from veritas.tools import tools
import orchestrator_class as orchestrator


def configure_device(task, oc, host_vars, template, path, dry_run):

    if host_vars:
        task.run(
            name="load_vars",
            task=oc.load_vars,
            host_vars=host_vars,
        )

        task.run(
            name="load_hooks",
            task=oc.load_hooks,
        )

        task.run(
            name="run_preprocessing",
            task=oc.run_preprocessing,
        )

    task.run(
        name="render_template",
        task=oc.render_template,
        template=template,
        path=path,
    )

    if host_vars:
        task.run(
            name="run_postprocessing",
            task=oc.run_postprocessing,
        )

    task.run(
        name="configure_device",
        task=oc.configure_device,
        dry_run=dry_run
    )

    if not dry_run:
        task.run(
            name="write_config",
            task=oc.write_config
        )

def main(args_list=None):

    # init variables
    additional_select = []
    host_vars = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='script_bakery.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    parser.add_argument('--scrapli-loglevel', type=str, required=False, default="error", help="Scrapli loglevel")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    # what device
    parser.add_argument('--devices', type=str, required=True, help="IP or name of device")
    # we need username and password if the config is retrieved by the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False)
    parser.add_argument('--password', type=str, required=False)
    parser.add_argument('--profile', type=str, required=False)
    # which TCP port should we use to connect to devices
    parser.add_argument('--port', type=int, default=22, help="TCP Port to connect to device", required=False)

    #
    # add subparsers
    #

    # add subparsers
    subparsers = parser.add_subparsers(dest='command')
    parser_download = subparsers.add_parser('download', help='download device configs')
    parser_configure = subparsers.add_parser('configure', help='configure devices using templates')
    parser_replace = subparsers.add_parser('replace', help='replace existing config on device with new config')

    # download device configs
    parser_download.add_argument('--type', type=str, default="running", required=False, 
                                 help="which type of config to download")
    parser_download.add_argument('--directory', type=str, default="configs", required=False, 
                                 help="directory to save config to")

    # configure devices using templates
    parser_configure.add_argument('--vars', type=str, required=False, help="host variables to use")
    parser_configure.add_argument('--path', type=str, default="./templates", required=False, 
                                  help="path where to find templates")
    parser_configure.add_argument('--template', type=str, required=True, help="template to use")
    parser_configure.add_argument('--dry-run', action='store_true', help="Make no changes, just print")

    # replace existing config on device with new config
    parser_replace.add_argument('--directory', type=str, default="configs", required=False, 
                                help="directory to load config from")

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    if not args.profile and not args.username:
        sys.exit('no profile or username given')

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
        app='backup_configs',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=False)

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('script_bakery', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file found and no salt.yaml file found')
            return
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # load profiles
    profile_config = tools.get_miniapp_config('script_bakery', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=args.profile,
        username=args.username,
        password=args.password,
        ssh_key=None)

    # the orchestrator object to start the tasks
    oc = orchestrator.Orchestrator()

    # load host variables
    if 'vars' in args and args.vars:
        logger.debug(f'loading host variables from {args.vars}')
        host_vars = oc.load_yaml_file(args.vars)

        # check if we have to add some select variable to the host_vars
        if host_vars.get('general',{}).get('sot',{}).get('select',[]):
            additional_select = host_vars['general']['sot']['select']
            if isinstance(additional_select, str):
                additional_select = [additional_select]
            logger.debug(f'additional select: {additional_select}')

    groups = {'net': {'data': {'key': 'value'} }}

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(profile=profile, result='result', parse=False) \
        .init_nornir(select=['custom_field_data'] + additional_select, groups=groups, host_groups=['cf_net'])

    # debug inventory
    logger.debug(f'inventory: {nr.inventory.hosts}')
    logger.debug(f'groups: {nr.inventory.groups}')

    if args.command == "download":
        results = nr.run(
            name="download_config", 
            task=oc.download_config,
            path=args.directory,
            config_type=args.type, 
        )
    elif args.command == "replace":
        results = nr.run(
                name="replace_config", 
                task=oc.replace_config,
                path=args.directory 
        )
        print_result(results)
    elif args.command == "configure":
        results = nr.run(
            name="configure_device", 
            task=configure_device,
            oc=oc,
            host_vars=host_vars,
            template=args.template,
            path=args.path,
            dry_run=args.dry_run
        )
        #print_result(results)

if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../script_bakery')
    import send_commands as sc

    sc.main(['--profile', 'default', 
             '--loglevel', 'debug',
             '--devices', 'name=lab.local'])


    """
    main()
