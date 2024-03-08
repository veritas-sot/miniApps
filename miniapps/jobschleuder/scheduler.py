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
from veritas.tools import tools
import veritas.logging
from veritas.sot import sot as veritas_sot


def call_job(channel, queue, cmd, args):
    message = {'cmd': cmd, 'args': args}
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

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = veritas_sot.Sot(token=jobschleuder_config['sot']['token'], 
                          url=jobschleuder_config['sot']['nautobot'],
                          ssl_verify=jobschleuder_config['sot'].get('ssl_verify', False),
                          debug=False)

    rabbitmq_config = jobschleuder_config.get('rabbitmq',{})
    rabbitmq_host = rabbitmq_config.get('host', 'localhost')
    rabbitmq_port = rabbitmq_config.get('port', 5672)
    rabbitmq_queue = rabbitmq_config.get('queue')

    logger.bind(extra="rabbitmq").info(f'rabbit: {rabbitmq_host}:{rabbitmq_port} queue: {rabbitmq_queue}')

    credentials = pika.PlainCredentials('admin','admin')
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=rabbitmq_host,
            port=rabbitmq_port,
            credentials=pika.PlainCredentials('admin','admin')
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue=rabbitmq_queue, durable=True)

    with open(args.jobs) as f:
        jobs = yaml.safe_load(f.read())
    
    for job_description in jobs.get('jobs'):
        job_id = job_description.get('id')
        job_schedule = job_description.get('schedule')
        job_cmd = job_description.get('job')
        job_arguments = job_description.get('arguments')

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
                       cmd=job_cmd,
                       args=job_arguments)

    while True:
        schedule.run_pending()
        all_jobs = schedule.get_jobs()
        print(all_jobs)
        time.sleep(1)

if __name__ == "__main__":
    main()