#!/usr/bin/env python

import argparse
import sys
import os
import importlib
from loguru import logger

# veritas
from veritas.tools import tools
import veritas.plugin


def main():

    parser = argparse.ArgumentParser()

    # we do not have all arguments at this point. So we have to set the config file here
    configfile = "dispatcher.yaml"
    name_of_dispatcher = None

    # set the config file
    args = sys.argv[1:]
    for arg in args:
        if arg == '--config':
            # get config file and remove it from args
            configfile = args.pop()
            args.remove('--config')
        elif args == '--dispatcher':
            # get dispatcher plugin and remove it from args
            name_of_dispatcher = args.pop()
            args.remove('--dispatcher')

    # the user can enter a different config file
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    dispatcher_config = tools.get_miniapp_config('dispatcher', BASEDIR, configfile)
    if not dispatcher_config:
        print('unable to read config')
        sys.exit()

    package = dispatcher_config.get('dispatcher',{}).get('plugin_dir', 'plugins')
    subpackage = dispatcher_config.get('dispatcher',{}).get('plugin', 'dispatcher_rabbitmq')
    # overwrite dispatcher plugin if set
    subpackage = name_of_dispatcher if name_of_dispatcher else subpackage
    logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
    #try:
    importlib.import_module(f'{package}.{subpackage}')
    #except Exception as exc:
    #    logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

    # load plugin
    plugin = veritas.plugin.Plugin()
    call = plugin.get('plugins', 'dispatcher')
    if callable(call):
        dispatcher = call(dispatcher_config)
        dispatcher.set_args(parser)
        args = parser.parse_args(args)
        dispatcher.start(args)
    else:
        logger.error(f'could not call method {call}')


if __name__ == "__main__":
    main()