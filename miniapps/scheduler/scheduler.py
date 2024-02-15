#!/usr/bin/env python

import argparse
import importlib
import sys
import os
import pandas as pd
import time
import schedule
import traceback
import re
import getpass
from crontab import CronTab
from loguru import logger
from rich.console import Console as RichConsole
from rich.table import Table as RichTable
from datetime import datetime, timezone

# veritas
import veritas.logging
from veritas.cron import Scheduler
from veritas.tools import tools

task_register = {}

def load_task(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def print_table(df, title):
    table = RichTable(title=title)
    rows = df.values.tolist()
    rows = [[str(el) for el in row] for row in rows]
    columns = df.columns.tolist()

    for column in columns:
        table.add_column(column)

    for row in rows:
        table.add_row(*row, style='bright_green')

    console = RichConsole()
    console.print(table)

def run_job(job_id, scheduler):
    started = datetime.now(timezone.utc)
    started_int = started.strftime('%s')
    func = task_register[job_id]
    logger.debug(f'running job {job_id}')
    try:
        func(no_decorator=True)
        finished = datetime.now(timezone.utc)
        finished_int = finished.strftime('%s')
        scheduler.add_run(job_id, started, started_int, finished, finished_int, True, '')
    except Exception as exc:
        logger.critical(f'job {job_id} failed; {exc}')
        finished = datetime.now(timezone.utc)
        finished_int = finished.strftime('%s')
        scheduler.add_run(job_id, started, started_int, finished, finished_int, False, traceback.format_exc())

def schedule_tasks(args):

    # every().day.at("10:30")
    every_at = re.compile('^every\((.*?)\)\.(\w+)\.at\("(.*?)"\)$')
    every_do = re.compile('^every\((.*?)\)\.(\w+)$')
    scheduler = Scheduler()
    jobs = scheduler.get_all_tasks()
    for job in jobs:

        # get values from database
        job_id = job.get('id')
        filename = job.get('filename')
        module_name = job.get('module_name')
        function = job.get('function')
        job_schedule = job.get('schedule')
        name = job.get('filename').rsplit('/')[-1].replace('.py','')
        logger.debug(f'file={filename} module={module_name} function={function} schedule={job_schedule}')

        # register job
        module = load_task(name, filename)
        func = getattr(module, function)
        logger.debug(f'register job {job_id}')
        task_register[job_id] = func

        match_every_at = every_at.match(job_schedule)
        if match_every_at:
            interval = match_every_at.group(1)
            if len(interval) == 0:
                interval = 0
            unit = match_every_at.group(2)
            at = match_every_at.group(3)
            if callable(func):
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
                    job.do(run_job, job_id=job_id, scheduler=scheduler)
                else:
                    logger.error(f'failed to convert {at} to datetime')
            else:
                logger.error(f'function {function} is not callable in {module_name}')
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
                if callable(func):
                    logger.debug(f'schedule job {job_id} every({interval}).{unit}')
                    job = schedule.Job(interval=int(interval), scheduler=schedule)
                    job.unit = unit
                    if start_day:
                        job.start_day = start_day
                    job.do(run_job, job_id=job_id, scheduler=scheduler)
                else:
                    logger.error(f'function {function} is not callable in {module_name}')

    while True:
        schedule.run_pending()
        all_jobs = schedule.get_jobs()
        print(all_jobs)
        time.sleep(1)

def cli(args):
    scheduler = Scheduler()
    if args.show_jobs:
        jobs = scheduler.get_all_tasks()
        df = pd.DataFrame(jobs)
        print_table(df=df, title='Active Jobs')
    elif args.show_runs:
        runs = scheduler.get_all_runs()
        df = pd.DataFrame(runs)
        print_table(df=df, title='Runs')
    elif args.show_failed:
        failed = scheduler.get_failed_runs()
        df = pd.DataFrame(failed)
        print_table(df=df, title='Failed runs')
    elif args.deregister:
        list_to_deregister = args.deregister.split(',')
        for deregister in list_to_deregister:
            logger.debug(f'deregistering job {deregister}')
            success = scheduler.deregister_task(deregister)
            if success:
                print(f'deregistered job {deregister}')
            else:
                print(f'failed to deregister job {deregister}')
    elif args.deregister_all:
        success = scheduler.deregister_all_tasks()
        if success:
            print('deregistered all jobs')
        else:
            print('failed to deregister all jobs')

def register(args):
    scheduler = Scheduler()
    if args.id:
        success = scheduler.reschedule_task(args.id, args.schedule)
        if success:
            print(f'job {args.id} rescheduled to {args.schedule}')
    else:
        success = scheduler.register_task(args.filename, args.module, args.function, args.schedule, args.args)
        if success:
            print(f'job {args.filename} registered; scheduled at {args.schedule}')

def add_to_cron(args):

    hour_every = re.compile('^hour\.every\((\d+)\)$')
    hour_on = re.compile('^hour\.on\((.*?)\)$')
    hour_also_on = re.compile('^hour\.also\.on\((.*?)\)$')
    dow_on = re.compile('^dow\.on\((.*?)\)$')
    month_during = re.compile('^month\.during\((.*?)\)$')
    set_all = re.compile('^set_all\((.*?)\)$')

    username = args.username if args.username else getpass.getuser()
    job_args = args.args if args.args else ""
    cmd = f'{sys.executable} {args.job} {job_args}'
    logger.debug(f'adding the job to the crontab of {username}')
    logger.debug(f'the python interpreter is {sys.executable}')
    logger.debug(f'cmd={cmd}')

    cron = CronTab(user=username)
    if args.list:
        for job in cron:
            print(job)
        return

    # check if command already exists
    existing_jobs = cron.find_command('python')
    for job in existing_jobs:
        if cmd in str(job):
            if args.remove:
                cron.remove(job)
                cron.write()
                print('job removed')
            elif args.disable:
                job.enable(False)
                cron.write()
                print('job disabled')
            elif args.enable:
                job.enable(True)
                cron.write()
                print('job enabled')
            else:
                logger.info(f'the command {cmd} already exist in the crontab')
            return
    if args.remove:
        print(f'job {args.job} not found in crontag')
        return

    job = cron.new(command=cmd, comment='added by veritas.scheduler')

    # set schedule
    schedules = args.schedule.split(';')
    for sched in schedules:
        match = hour_every.match(sched)
        if match:
            every = match.group(1)
            logger.debug(f'found hour.every({every}) match')
            job.hour.every(every)
        match = hour_on.match(sched)
        if match:
            on = match.group(1)
            logger.debug(f'found hour.on({on}) match')
            job.hour.on(on)
        match = hour_also_on.match(sched)
        if match:
            on = match.group(1)
            logger.debug(f'found hour.also.on({on}) match')
            job.hour.also.on(on)
        match = dow_on.match(sched)
        if match:
            on = match.group(1)
            logger.debug(f'found dow.on({on}) match')
            job.dow.on(on)
        match = month_during.match(sched)
        if match:
            during = match.group(1)
            during_list = during.split(',')
            logger.debug(f'found month.during({during}) match list={during_list}')
            job.month.during(during_list[0],during_list[1])
        match = set_all.match(sched)
        if match:
            set_all = match.group(1)
            logger.debug(f'found set_all({set_all}) match')
            job.setall(set_all)

    cron.write()

def main():

    parser = argparse.ArgumentParser()
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="updater config file")
    parser.add_argument('--debug-veritas', action='store_true', help='enable veritas debug logging')

    # add subparsers
    subparsers = parser.add_subparsers(dest='command')
    parser_schedule = subparsers.add_parser('schedule', help='schedule devices')
    parser_cli = subparsers.add_parser('cli', help='schedule admin cli')
    parser_register = subparsers.add_parser('register', help='register new job')
    parser_cron = subparsers.add_parser('cron', help='add job to crontab')

    # schedule commands
    parser_schedule.add_argument('--run', action='store_true', help='run scheduled jobs')

    # cli commands
    parser_cli.add_argument('--deregister', type=str, required=False, help="deregister job")
    parser_cli.add_argument('--deregister-all', action='store_true', required=False, help="deregister all jobs")
    parser_cli.add_argument('--show-jobs', action='store_true', help='show all schedules jobs')
    parser_cli.add_argument('--show-runs', action='store_true', help='show all runs')
    parser_cli.add_argument('--show-failed', action='store_true', help='show failed runs')

    # register new jobs
    parser_register.add_argument('--id', type=str, required=False, help="reschedule job id")
    parser_register.add_argument('--filename', type=str, required=False, help="filename of the job")
    parser_register.add_argument('--module', type=str, required=False, help="module of the job")
    parser_register.add_argument('--function', type=str, required=False, help="function of job to call")
    parser_register.add_argument('--args', type=str, required=False, help="additional arguments")
    parser_register.add_argument('--schedule', type=str, required=False, help="when to schedule the job")

    # crontab
    parser_cron.add_argument('--job', type=str, required=True, help="filename of the job")
    parser_cron.add_argument('--args', type=str, required=False, help="arguments of the job")
    parser_cron.add_argument('--username', type=str, required=False, help="the username of the cron")
    parser_cron.add_argument('--schedule', type=str, required=True, help="when to schedule the job")
    parser_cron.add_argument('--remove', action='store_true', help='remove specified job')
    parser_cron.add_argument('--disable', action='store_true', help='disable specified job')
    parser_cron.add_argument('--enable', action='store_true', help='enable specified job')
    parser_cron.add_argument('--list', action='store_true', help='list all jobs')

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    kobold_config = tools.get_miniapp_config('scheduler', BASEDIR, args.config)
    if not kobold_config:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=kobold_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='kobold',
        uuid=args.uuid)

    if args.command == 'schedule':
        schedule_tasks(args)
    elif args.command == 'cli':
        cli(args)
    elif args.command == 'register':
        register(args)
    elif args.command == 'cron':
        add_to_cron(args)

if __name__ == "__main__":
    main()
