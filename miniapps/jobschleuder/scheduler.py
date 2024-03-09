#!/usr/bin/env python

import argparse
import urllib3
import os
import sys
import json
import yaml
import pika
import schedule
import re
import time
import importlib
from datetime import datetime
from loguru import logger

# veritas
import rabbitmq
import veritas.logging
from veritas.tools import tools
from veritas.sot import sot as veritas_sot


def import_plugins(jobschleuder_config):
    # import plugins
    plugins = jobschleuder_config.get('preprocessing',{})
    print(plugins)
    for plugin in plugins:
        package = plugins.get(plugin).get('plugin_dir')
        subpackage = plugins.get(plugin).get('plugin')
        logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

def call_job(channel, queue, preprocessing, cmd, args):

    jobs = None
    if preprocessing:
        logger.bind(extra="preprocessing").debug(f'calling preprocessing {preprocessing}')
        try:
            plugin = veritas.plugin.Plugin()
            plugin_func = plugin.get_jobschleuder_plugin(preprocessing)
            if callable(plugin_func):
                jobs = plugin_func(**args)
            else:
                logger.error(f'could not call plugin command {cmd}')
        except Exception as exc:
            logger.bind(extra="preprocessing").error(f'failed to call preprocessing {preprocessing}; got exception {exc}')
            raise exc
    elif not jobs:
        jobs = [{'cmd': cmd, 'args': args}]

    if len(jobs) == 0:
        logger.info('got an empty list of jobs')
        return

    for job in jobs:
        message = {'cmd': job.get('cmd'), 'args': job.get('args')}
        logger.debug(f'calling job {job.get("cmd")} with args {job.get("args")}')
        channel.basic_publish(
            exchange='',
            routing_key=queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent
            )
        )

def main(args_list=None):

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # every().day.at("10:30")
    every_at = re.compile('^every\((.*?)\)\.(\w+)\.at\("(.*?)"\)$')
    every_do = re.compile('^every\((.*?)\)\.(\w+)$')

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--config', help='config file', default='jobschleuder.yaml')
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    parser.add_argument('--debug-veritas', help='debug veritas', action='store_true')
    parser.add_argument('--jobs', help='filename of jobs to schedule', default='./jobs/jobs.yaml', required=False)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

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

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=jobschleuder_config['sot']['token'], 
                          url=jobschleuder_config['sot']['nautobot'],
                          ssl_verify=jobschleuder_config['sot'].get('ssl_verify', False),
                          debug=False)

    # open rabbitmq
    channel, rabbitmq_queue = rabbitmq.open_rabbitmq(jobschleuder_config.get('rabbitmq'))

    with open(args.jobs) as f:
        jobs = yaml.safe_load(f.read())

    for job_description in jobs.get('jobs'):
        job_id = job_description.get('id')
        job_schedule = job_description.get('schedule')
        job_cmd = job_description.get('job')
        job_arguments = job_description.get('arguments')
        job_preprocessing = job_description.get('preprocessing')

        if job_arguments.get('sot',False):
            job_arguments['sot'] = sot

        logger.bind(extra="schedule").debug(f'job_id: {job_id} schedule: {job_schedule}')

        match_every_at = every_at.match(job_schedule)
        if match_every_at:
            interval = match_every_at.group(1)
            if len(interval) == 0:
                interval = 0
            unit = match_every_at.group(2)
            at = match_every_at.group(3)

            logger.bind(extra="every_at").debug(f'schedule job {job_id} every({interval}).{unit}.at({at})')
            if unit in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']:
                logger.debug(f'setting start_day to {unit} and unit to weeks')
                start_day = unit
                unit = 'weeks'
            else:
                start_day = None
            at_time = datetime.strptime(at, '%H:%M').time()
            if at_time:
                job = schedule.Job(interval=int(interval), scheduler=schedule)
                job.unit = unit
                if start_day:
                    job.start_day = start_day
                job.at_time = at_time
                job.do(call_job, 
                       channel=channel,
                       queue=rabbitmq_queue,
                       preprocessing=job_preprocessing,
                       cmd=job_cmd,
                       args=job_arguments)
            else:
                logger.error(f'failed to convert {at} to datetime')

        else:
            match_every_do = every_do.match(job_schedule)
            if match_every_do:
                interval = match_every_do.group(1)
                unit = match_every_do.group(2)
                if len(interval) == 0:
                    interval = 0
                if unit in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']:
                    logger.debug(f'setting start_day to {unit} and unit to weeks')
                    start_day = unit
                    unit = 'weeks'
                else:
                    start_day = None

                logger.bind(extra="every_do").debug(f'schedule job {job_id} every({interval}).{unit}')
                job = schedule.Job(interval=int(interval), scheduler=schedule)
                job.unit = unit
                if start_day:
                    job.start_day = start_day
                job.do(call_job, 
                       channel=channel,
                       queue=rabbitmq_queue,
                       preprocessing=job_preprocessing,
                       cmd=job_cmd,
                       args=job_arguments)

    while True:
        schedule.run_pending()
        schedule.get_jobs()
        time.sleep(1)

if __name__ == "__main__":
    main()