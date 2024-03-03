#!/usr/bin/env python

import argparse
import os
import sys
import json
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv
from nornir_utils.plugins.functions import print_result
from nornir_salt.plugins.functions import TabulateFormatter, ResultSerializer
from nornir.core.task import Task

# veritas
import veritas.logging
import veritas.profile
import configmanagement_class as configmanagement
import config_context as cc
from veritas.sot import sot as veritas_sot
from veritas.tools import tools


def deploy_configs(task, cm, host_vars, template, path, dry_run):

    if host_vars:
        task.run(
            name="load_vars",
            task=cm.load_vars,
            host_vars=host_vars,
        )

        task.run(
            name="load_hooks",
            task=cm.load_hooks,
        )

        task.run(
            name="run_preprocessing",
            task=cm.run_preprocessing,
        )

    task.run(
        name="render_template",
        task=cm.render_template,
        template=template,
        path=path,
    )

    if host_vars:
        task.run(
            name="run_postprocessing",
            task=cm.run_postprocessing,
        )

    task.run(
        name="configure_device",
        task=cm.configure_device,
        dry_run=dry_run
    )

    if not dry_run:
        task.run(
            name="write_config",
            task=cm.write_config
        )

def intended_config(cm, nr, directory, set_timestamp, section, output):
    if set_timestamp:
        now = datetime.now()
        dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'
    else:
        dt = ""

    result = nr.run(
        name="intended_config", 
        task=cm.render_intended_config,
    )
    serialized_result = ResultSerializer(result, add_details=True)
    for hostname, value in serialized_result.items():
        intended_config = value.get('template_file',{}).get('result')
        if intended_config:
            if output == "stdout":
                print(intended_config)
            else:
                filename = f'{directory}/{hostname}{dt}.intended.config'
                with open(filename, 'w') as f:
                    f.write(intended_config)
                
def get_device_config(task:Task, cm:configmanagement, config_type:str, directory:str, 
                      set_timestamp:bool, section:list|None, output:str):

    startup_config = None
    running_config = None
    running_section = []
    startup_section = []
    hostname = str(task.host)
    dt = ""

    # get the config(s) from the device
    if 'running' in config_type and 'startup' in config_type:
        running_config, startup_config = cm.get_config_from_device(task, 'all')
    if 'running' in config_type:
        running_config = cm.get_config_from_device(task, 'running')
    elif 'startup' in config_type:
        startup_config = cm.get_config_from_device(task, 'startup')

    #
    # get section
    #
    if section and len(section) > 0:
        for sct in section:
            if 'running' in config_type:
                running_section += cm.get_section(running_config, sct)
            if 'startup' in config_type:
                startup_section += cm.get_section(startup_config, sct)

    #
    # set section to config lines
    #
    if len(running_section) > 0:
        running_config = '\n'.join(running_section)
    if len(startup_section) > 0:
        startup_config = '\n'.join(startup_section)

    #
    # write to file or print
    #
    # get current date and time
    if set_timestamp:
        now = datetime.now()
        dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'

    if output == "stdout":
        if running_config:
            print(running_config)
        if startup_config:
            print(startup_config)
    else:
        if running_config:
            filename = f'{directory}/{task.host}{dt}.running.config'
            cm.write_content_to_disk(task, running_config, hostname, filename)
        if startup_config:
            filename = f'{directory}/{task.host}{dt}.startup.config'
            cm.write_content_to_disk(task, startup_config, hostname, filename)

def config_context(task:Task, cm:configmanagement, sot:veritas_sot, 
                   get_context:bool, set_context:bool, update_context:bool,
                   use_config:bool=False, device_configs:str="./device_configs", 
                   template_dir:str="./config_context"):

    if use_config:
        try:
            filename = f'{device_configs}/{task.host}.running.config'
            logger.debug(f'reading config from file {filename}')
            with open(filename, 'r') as f:
                device_config = f.read()
        except Exception as exc:
            logger.error(f'could not read file {use_config}; got exception {exc}')
            return
    else:
        device_config = cm.get_config_from_device(task, config_type="running")

    device_context = task.run(
        name="get_config_context",
        task=cc.get_config_context,
        cm=cm,
        device_config=device_config,
        template_dir=template_dir
    )

    if get_context:
        print(json.dumps(device_context.result, indent=4))
    if set_context or update_context:
        task.run(
            name="set_config_context",
            task=cc.set_device_config_context,
            cm=cm,
            sot=sot,
            update_context=update_context,
            device_context=device_context.result
        )

def main(args_list=None):

    # init variables
    additional_select = []
    host_vars = None

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='configmanagement.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
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
    parser_get = subparsers.add_parser('get', help='download device configs or render intended config')
    parser_deploy = subparsers.add_parser('deploy', help='configure devices using templates')
    parser_replace = subparsers.add_parser('replace', help='replace existing config on device with new config')
    parser_config_context = subparsers.add_parser('context', help='get and set config context')

    #
    # get configs
    #
    parser_get.add_argument('--running', action='store_true', help="get running config")
    parser_get.add_argument('--startup', action='store_true', help="get startup config")
    parser_get.add_argument('--intended', action='store_true', help="render intended config")
    parser_get.add_argument('--set-timestamp', action='store_true', help="set timestamp in filename")
    parser_get.add_argument('--config-dir', type=str, required=False, help="directory to save configs to")
    parser_get.add_argument('--section', type=str, nargs="*", required=False, 
                            help="get specific section of config")
    parser_get.add_argument('--output', type=str, default="write_file", required=False, 
                            choices=['stdout', 'write_file'], help="print or write to file")                 

    #
    # deploy devices using templates
    #
    parser_deploy.add_argument('--vars', type=str, required=False, help="host variables to use")
    parser_deploy.add_argument('--template-dir', type=str, required=False, help="path where to find templates")
    parser_deploy.add_argument('--template', type=str, required=True, help="template to use")
    parser_deploy.add_argument('--dry-run', action='store_true', help="Make no changes, just print")

    #
    # replace existing config on device with new config
    #
    parser_replace.add_argument('--config-dir', type=str, default="configs", required=False, 
                                help="directory to load configs from")

    #
    # get and set config context
    #
    parser_config_context.add_argument('--get', action='store_true', help="show config context")
    parser_config_context.add_argument('--set', action='store_true', help="set config context in SOT")
    parser_config_context.add_argument('--update', action='store_true', help="update config context in SOT")
    parser_config_context.add_argument('--config-from-disk', action='store_true', 
                                       help="use file instead of getting config from device")
    parser_config_context.add_argument('--config-dir', type=str, required=False, 
                                       help="directory to load configs from")
    parser_config_context.add_argument('--template-dir', type=str, default="./config_context", 
                                       required=False, help="directory to get config context from")

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    if not args.profile and not args.username:
        sys.exit('no profile or username given')

    if 'directory' in args and not os.path.exists(args.directory):
        os.makedirs(args.directory)

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    local_config_file = tools.get_miniapp_config('configmanagement', BASEDIR, args.config)
    if not local_config_file:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='config_management',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=local_config_file['sot']['token'], 
                          url=local_config_file['sot']['nautobot'],
                          ssl_verify=local_config_file['sot'].get('ssl_verify', False),
                          debug=True)

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('configmanagement', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file found and no salt.yaml file found')
            return
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # load profiles
    profile_config = tools.get_miniapp_config('configmanagement', BASEDIR, 'profiles.yaml')
    # save profile for later use
    profile = veritas.profile.Profile(
        profile_config=profile_config, 
        profile_name=args.profile,
        username=args.username,
        password=args.password,
        ssh_key=None)

    # the configmanagement object to start the tasks
    cm = configmanagement.ConfigManagement()

    # load host variables
    if 'vars' in args and args.vars:
        logger.debug(f'loading host variables from {args.vars}')
        host_vars = cm.load_yaml_file(args.vars)

        # check if we have to add some select variable to the host_vars
        if host_vars.get('general',{}).get('sot',{}).get('select',[]):
            additional_select = host_vars['general']['sot']['select']
            if isinstance(additional_select, str):
                additional_select = [additional_select]
            logger.debug(f'additional select: {additional_select}')

    if args.command == "get" and args.intended:
        additional_select.append('config_context')
        additional_select.append('interfaces')
    if args.command == "context":
        additional_select.append('config_context')

    # example group....
    groups = {'net': {'data': {'key': 'value'} }}

    # init nornir
    nr = sot.job.on(args.devices) \
        .set(profile=profile, result='result', parse=False) \
        .init_nornir(select=['custom_field_data'] + additional_select, groups=groups, host_groups=['cf_net'])

    # debug inventory
    logger.debug(f'inventory: {nr.inventory.hosts}')
    logger.debug(f'groups: {nr.inventory.groups}')

    if args.command == "get":
        # Directory from which we read the configurations or to which we write the configurations
        device_configs = args.config_dir if args.config_dir else \
            local_config_file.get('configmanagement',{}).get('defaults',{}).get('configs')

        if args.intended:
            intended_config(cm, nr, args.config_dir, args.set_timestamp, args.section, args.output)
        if args.running or args.startup:
            config_type = []
            if args.running:
                config_type.append('running')
            if args.startup:
                config_type.append('startup')

            # start workflow
            logger.info('starting workflow: get_device_config')
            results = nr.run(
                name="get_device_config", 
                task=get_device_config,
                cm=cm,
                config_type=config_type,
                directory=device_configs,
                set_timestamp=args.set_timestamp,
                section=args.section,
                output=args.output
            )
    elif args.command == "replace":
        results = nr.run(
                name="replace_config", 
                task=cm.replace_config,
                path=args.config_dir 
        )
        print_result(results)
    elif args.command == "deploy":
        # Directory from which we read the configurations or to which we write the configurations
        template_dir = args.template_dir if args.template_dir else \
            local_config_file.get('configmanagement',{}).get('defaults',{}).get('templates',{}).get('jobs')

        results = nr.run(
            name="deploy_configs", 
            task=deploy_configs,
            cm=cm,
            host_vars=host_vars,
            template=args.template,
            path=template_dir,
            dry_run=args.dry_run
        )
        # print_result(results)
        print(TabulateFormatter(results))
        # result_dictionary = ResultSerializer(results, add_details=True)
        # print(json.dumps(result_dictionary, indent=4))
    elif args.command == "context":

        # Directory from which we read the configurations or to which we write the configurations
        device_configs = args.config_dir if args.config_dir else \
            local_config_file.get('configmanagement',{}).get('defaults',{}).get('configs')

        template_dir = args.template_dir if args.template_dir else \
            local_config_file.get('configmanagement',{}).get('defaults',{}).get('config_context')

        results = nr.run(
                name="workflow_config_context", 
                task=config_context,
                cm=cm,
                sot=sot,
                get_context=args.get,
                set_context=args.set,
                update_context=args.update,
                use_config=args.config_from_disk,
                device_configs=device_configs,
                template_dir=args.template_dir
        )
        #serialized_result = ResultSerializer(results, add_details=True)
        #print(serialized_result)

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
