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

def call_plugin(channel, method, properties, body, additional_args):
    
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
    
    channel.basic_ack(delivery_tag=method.delivery_tag)

def worker(jobschleuder_config):

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

    # import jobschleuder plugins
    import_plugins(jobschleuder_config)

    # init plugin
    plugin = veritas.plugin.Plugin()

    # initialize additional args
    # additional arguments are used to pass configs to the call_plugin function
    # we get those arguments by calling the 'on_startup' function of the plugin
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
    logger.info(' [*] Waiting for messages. To exit press CTRL+C')

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=rabbitmq_queue, 
        on_message_callback=lambda channel, method, properties, body: call_plugin(channel, method, properties, body, additional_args)
    )
    channel.start_consuming()

