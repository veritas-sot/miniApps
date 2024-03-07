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
from datetime import datetime
from loguru import logger

# veritas
from veritas import tools
import veritas.logging
from veritas.cron import Scheduler


def call_job(channel, rabbitmq_config, job):
    logger.debug(f'publishing job {job}')
    channel.basic_publish(
        exchange='',
        routing_key=rabbitmq_config.get('queue'),
        body=json.dumps(job),
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
    scheduler = Scheduler()

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--config', help='config file', default='config.yaml')
    parser.add_argument('--loglevel', help='loglevel', default='INFO')
    parser.add_argument('--loghandler', help='loghandler', default='console')
    parser.add_argument('--uuid', help='uuid', default='onboarding')
    parser.add_argument('--debug-veritas', help='debug veritas', action='store_true')
    parser.add_argument('--profile', help='profile', default='default')
    parser.add_argument('--username', help='username', default=None)
    parser.add_argument('--password', help='password', default=None)

    parser.add_argument('--jobs', help='filename of jobs to schedule', default='./jobs/jons.yaml', required=False)

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    jobschleuder_config = tools.get_miniapp_config('onboarding', BASEDIR, args.config)
    if not jobschleuder_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=jobschleuder_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='onboarding',
        uuid=args.uuid)

    rabbitmq_config = jobschleuder_config.get('rabbitmq',{})

    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=rabbitmq_config.get('host', 'localhost'),
            port=rabbitmq_config.get('port', 5672),
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue=rabbitmq_config.get('queue'), durable=True)

    with open(args.job) as f:
        jobs = yaml.safe_load(f.read())
    
    for job in jobs:
        job_id = job.get('id')
        job_schedule = job.get('schedule')

        match_every_at = every_at.match(job_schedule)
        if match_every_at:
            interval = match_every_at.group(1)
            if len(interval) == 0:
                interval = 0
            unit = match_every_at.group(2)
            at = match_every_at.group(3)

            logger.debug(f'schedule job {job_id} every({interval}).{unit}.at({at})')
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
                       rabbitmq_config=rabbitmq_config,
                       job=job,
                       scheduler=scheduler)
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

                logger.debug(f'schedule job {job_id} every({interval}).{unit}')
                job = schedule.Job(interval=int(interval), scheduler=schedule)
                job.unit = unit
                if start_day:
                    job.start_day = start_day
                job.do(call_job, 
                       channel=channel,
                       rabbitmq_config=rabbitmq_config,
                       job=job,
                       scheduler=scheduler)

    while True:
        schedule.run_pending()
        all_jobs = schedule.get_jobs()
        print(all_jobs)
        time.sleep(1)

if __name__ == "__main__":
    main()