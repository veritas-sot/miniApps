import yaml
import json
import re
from loguru import logger
from datetime import datetime, date, timedelta

# local
import database_handling

days_enum = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 4, 'friday': 5, 'saturday': 6, 'sunday': 7}

def init(database):

    # regex
    # every().day.at("10:30")
    every_at = re.compile('^every\((.*?)\)\.(\w+)\.at\("(.*?)"\)$')
    every_do = re.compile('^every\((.*?)\)\.(\w+)$')

    logger.bind(extra="init").debug('connect to database')
    cursor = database_handling.connect_to_db(database)

    sql = """SELECT jobs.job, jobs.preprocessing, jobs.arguments, registry.id, registry.schedule
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

        match_every_at = every_at.match(schedule)
        match_every_do = every_do.match(schedule)

        if match_every_at:
            interval = match_every_at.group(1)
            if len(interval) == 0:
                interval = 0
            unit = match_every_at.group(2)
            at = match_every_at.group(3)

            logger.bind(extra="every_at").debug(f'schedule job {job}({job_id}) every {interval} {unit} at {at}')
            if unit in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']:
                start_day = unit
                todays_date = date.today()
                weekday = todays_date.weekday()
                days_diff = (days_enum[start_day] - weekday) % 7
                schedule_at = f'{todays_date + timedelta(days_diff)} {at}'
                add_job_to_database(cursor, job_id, schedule_at)

        if match_every_do:
            interval = match_every_do.group(1)
            unit = match_every_do.group(2)
            if len(interval) == 0:
                interval = 0
            else:
                interval = int(interval)
            if unit in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']:
                logger.debug(f'setting start_day to {unit} and unit to weeks')
                start_day = unit
                unit = 'weeks'
            else:
                start_day = None

            todays_date = datetime.now()
            if unit == 'seconds':
                schedule_datetime = todays_date + timedelta(seconds=interval)
            elif unit == 'minutes':
                schedule_datetime = todays_date + timedelta(minutes=interval)
            elif unit == 'hours':
                schedule_datetime = todays_date + timedelta(hours=interval)
            elif unit == 'weeks':
                todays_date = date.today()
                weekday = todays_date.weekday()
                days_diff = (days_enum[start_day] - weekday) % 7
                schedule_datetime = todays_date + timedelta(days_diff)
            else:
                logger.error(f'unknown unit {unit}')

            schedule_at = schedule_datetime.strftime("%Y-%m-%d %H:%M:%S")
            logger.bind(extra="every_do").debug(f'schedule job {job}({job_id}) every {interval} {unit} schedule_at={schedule_at}')
            add_job_to_database(cursor, job_id, schedule_at)

    # commit data
    cursor.connection.commit()

def add_job_to_database(cursor, job_id, schedule):
    sql = """INSERT INTO schedule (job, next_run) VALUES (%s, %s) RETURNING id"""
    cursor.execute(sql, (job_id, schedule))
    return cursor.fetchone()['id']