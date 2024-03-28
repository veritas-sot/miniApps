import yaml
import json
import re
import pandas as pd
import time
import pika
import importlib
import psycopg2.extras
from croniter import croniter
from loguru import logger
from datetime import datetime, date, timedelta
from rich.console import Console as RichConsole
from rich.table import Table as RichTable

# local
import database_handling
import rabbitmq
import veritas.plugin
from veritas.sot import sot as veritas_sot


days_enum = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 4, 'friday': 5, 'saturday': 6, 'sunday': 7}

def init(database):

    # regex
    # every().day.at("10:30")
    every_at = re.compile('^every\((.*?)\)\.(\w+)\.at\("(.*?)"\)$')
    every_do = re.compile('^every\((.*?)\)\.(\w+)$')

    logger.bind(extra="init").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(database)

    sql = """SELECT jobs.job, jobs.preprocessing, jobs.arguments, registry.id as id, registry.schedule
             FROM jobs JOIN registry ON registry.job = jobs.id"""
    try:
        cursor.execute(sql, )
        jobs = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from database {exc}')
        return False
    
    for jb in jobs:
        job_id = jb.get('id')
        job = jb.get('job')
        preprocessing = jb.get('preprocessing')
        arguments = jb.get('arguments')
        schedule = jb.get('schedule')

        logger.bind(extra="init").debug(f'job={job} preprocessing={preprocessing} arguments={arguments} schedule={schedule}')

        # add job to schedule database
        base = datetime.now()
        iter = croniter(schedule, base)
        scheduled_at = iter.get_next(datetime)
        add_job_to_database(cursor, job_id, scheduled_at)

    # commit data
    cursor.connection.commit()

def show_jobs(database):
    logger.bind(extra="init").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(database)

    sql = """SELECT jobs.id, jobs.job, jobs.description as descr, jobs.preprocessing as pre, 
             jobs.postprocessing as post, jobs.arguments as args
             FROM jobs"""

    try:
        cursor.execute(sql, )
        jobs = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from database {exc}')
        return False
    
    df = pd.DataFrame(jobs)
    print_table(df=df, title='All Jobs')

def show_scheduled_jobs(database):
    logger.bind(extra="init").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(database)

    jobs = get_scheduled_jobs(cursor, where="schedule.next_run <= NOW()")
    df = pd.DataFrame(jobs)
    print_table(df=df, title='Current scheduled Jobs')

def show_all_scheduled_jobs(database):
    logger.bind(extra="init").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(database)

    jobs = get_scheduled_jobs(cursor)
    df = pd.DataFrame(jobs)
    print_table(df=df, title='All scheduled Jobs')

def run_now(jobschleuder_config, rid):
    logger.bind(extra="init").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(jobschleuder_config.get('database',{}))

    sql = """SELECT jobs.id, jobs.job, jobs.description as descr, jobs.preprocessing as pre, 
             jobs.postprocessing as post, jobs.arguments as args
             FROM jobs WHERE jobs.id = %s"""

    try:
        cursor.execute(sql, (str(rid), ))
        jobs = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from database {exc}')
        return False

    # import jobschleuder plugins
    import_plugins(jobschleuder_config)

    # open rabbitmq
    channel, rabbitmq_queue = rabbitmq.open_rabbitmq(jobschleuder_config.get('rabbitmq'))

    for job in jobs:
        cmd = job.get('job')
        preprocessing = job.get('pre')
        arguments = job.get('args')

        if arguments.get('sot',False):
            arguments['sot'] = get_sot(jobschleuder_config)

        logger.bind(extra="run").info(f'running {cmd} pre={preprocessing} args={arguments}')
        call_job(channel, rabbitmq_queue, preprocessing, cmd, arguments)

def schedule_jobs(jobschleuder_config, exit_after_run):
    # import jobschleuder plugins
    import_plugins(jobschleuder_config)

    # open rabbitmq
    channel, rabbitmq_queue = rabbitmq.open_rabbitmq(jobschleuder_config.get('rabbitmq'))

    logger.bind(extra="schedule").debug('connect to database')
    conn, cursor = database_handling.connect_to_db(jobschleuder_config.get('database',{}))

    # we need the SOT object to talk to the SOT
    # if you want to see more debug messages of the lib set 
    # debug to True
    sot = get_sot(jobschleuder_config)

    while True:
        jobs = get_scheduled_jobs(cursor, where="schedule.next_run <= NOW()")
        for job in jobs:
            cmd = job.get('job')
            job_id = job.get('rid')
            schedule_id = job.get('sid')
            preprocessing = job.get('pre')
            arguments = job.get('args')
            schedule = job.get('sched')

            # if we need the SOT add it to the arguments
            if arguments.get('sot',False):
                arguments['sot'] = get_sot(jobschleuder_config)

            # add new schedule entry to the database
            base = datetime.now()
            iter = croniter(schedule, base)
            scheduled_at = iter.get_next(datetime)
            logger.bind(extra='schedule').info(f'scheduling nextrun of {cmd} to {scheduled_at}')
            add_job_to_database(cursor, job_id, scheduled_at)

            # delete old entry
            delete_scheduled_job_from_database(cursor, schedule_id)

            # commit data
            cursor.connection.commit()

            # now send command to our rabbit queue
            logger.bind(extra='schedule').info(f'scheduling job {cmd}')
            call_job(channel, rabbitmq_queue, preprocessing, cmd, arguments)

        # strange behavior: If we do not commit the connection we do not see the data we have written
        # to the database. In my opinion, this seems to be a bug. We have commited the transaction
        # right after deleting the old entry
        cursor.connection.commit()
        if exit_after_run:
            logger.bind(extra="schedule").debug('exit...')
            return
        else:
            time.sleep(1)


#
# private methods
#

def add_job_to_database(cursor, job_id, schedule):
    sql = """INSERT INTO schedule (job, next_run) VALUES (%s, %s) RETURNING id"""
    cursor.execute(sql, (job_id, schedule))
    return cursor.fetchone()['id']

def delete_scheduled_job_from_database(cursor, sid):
    sql = """DELETE FROM schedule WHERE id = %s"""
    cursor.execute(sql, (str(sid), ))

def get_scheduled_jobs(cursor, where=None):
    sql = """SELECT jobs.id as job_id, jobs.job, jobs.description as descr, 
                    jobs.preprocessing as pre, jobs.arguments as args,
                    registry.id as rid, registry.schedule as sched,
                    schedule.id as sid, schedule.next_run as nextrun
             FROM registry 
             INNER JOIN schedule ON schedule.job = registry.id
             INNER JOIN jobs ON jobs.id = registry.job"""

    if where:
        sql += f' WHERE {where}'

    try:
        cursor.execute(sql, )
        return cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from database {exc}')
        return False

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

def import_plugins(jobschleuder_config):
    # import plugins
    plugins = jobschleuder_config.get('preprocessing',{})

    for plugin in plugins:
        package = plugins.get(plugin).get('plugin_dir')
        subpackage = plugins.get(plugin).get('plugin')
        logger.bind(extra='plugins').info(f'importing {package}.{subpackage}')
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.bind(extra='plugins').critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

def call_job(channel, rabbitmq_queue, preprocessing, cmd, args):

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
            routing_key=rabbitmq_queue,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent
            )
        )

def get_sot(jobschleuder_config):
    return veritas_sot.Sot(token=jobschleuder_config['sot']['token'], 
                           url=jobschleuder_config['sot']['nautobot'],
                           ssl_verify=jobschleuder_config['sot'].get('ssl_verify', False),
                           debug=False)
