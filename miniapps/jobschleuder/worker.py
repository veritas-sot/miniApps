#!/usr/bin/env python

import argparse
import urllib3
import os
import sys
import importlib
import json
from loguru import logger
from dotenv import load_dotenv

# veritas
from veritas.tools import tools
import rabbitmq
import veritas.profile
import veritas.logging
import veritas.plugin


def import_plugins(jobschleuder_config):
    # import plugins
    plugins = jobschleuder_config.get('plugins')
    for plugin in plugins:
        package = plugins.get(plugin).get('plugin_dir')
        subpackage = plugins.get(plugin).get('plugin')
        logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

def call_plugin(ch, method, properties, body, additional_args):
    
    # we need the plugin that we got from our additional args
    plugin = additional_args.get('plugin')

    try:
        job = json.loads(body.decode())
    except Exception as exc:
        logger.bind(extra="plugin").error(f'failed to decode message {body.decode}; got {exc}')

    cmd = job.get('cmd')
    args = job.get('args',{})
    if cmd in additional_args.get('configs',{}):
        args.update(additional_args.get('configs').get(cmd))
    plugin_func = plugin.get_jobschleuder_plugin(cmd)
    if callable(plugin_func):
        plugin_func(**args)
    else:
        logger.error(f'could not call plugin command {cmd}')
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main(args_list=None):

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    parser = argparse.ArgumentParser()
    # what to do
    # what to do
    parser.add_argument('--config', help='config file', default='jobschleuder.yaml')
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    parser.add_argument('--debug-veritas', help='debug veritas', action='store_true')
    parser.add_argument('--profile', help='profile', default='default')
    parser.add_argument('--username', help='username', default=None)
    parser.add_argument('--password', help='password', default=None)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug('reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug('no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('jobschleuder', BASEDIR, "salt.yaml")
        if not crypt_parameter:
            logger.error('no .env file and no salt.yaml file found')
            sys.exit()
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # read config
    jobschleuder_config = tools.get_miniapp_config('jobschleuder', BASEDIR, args.config)
    if not jobschleuder_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=jobschleuder_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='jobschleuder',
        uuid=args.uuid)

    # import jobschleuder plugins
    import_plugins(jobschleuder_config)

    # init plugin
    plugin = veritas.plugin.Plugin()

    # additional args
    additional_args = {'plugin': plugin, 'configs': {}}

    # load plugin configs
    all_plugins = plugin.get_registry('jobschleuder')
    for plgn in all_plugins:
        plugin_func = plugin.get_jobschleuder_plugin(f'{plgn}:on_startup')
        if callable(plugin_func):
            config = plugin_func()
            additional_args['configs'].update({plgn:config})

    # open rabbitmq
    channel, rabbitmq_queue = rabbitmq.open_rabbitmq(jobschleuder_config.get('rabbitmq'))
    print(' [*] Waiting for messages. To exit press CTRL+C')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=rabbitmq_queue, 
        on_message_callback=lambda ch, method, properties, body: call_plugin(ch, method, properties, body, additional_args)
    )
    channel.start_consuming()

if __name__ == "__main__":
    main()