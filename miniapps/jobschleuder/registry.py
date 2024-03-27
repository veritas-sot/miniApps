import yaml
import json
from loguru import logger

# local
import database_handling


def import_file(database, filename):
    try:
        logger.bind(extra="import").debug(f'reading {filename}')
        with open(filename) as f:
            jobs = yaml.safe_load(f.read())
    except Exception as exc:
        logger.error(f'failed to read {filename} got exception {exc}')
        return False

    logger.bind(extra="import").debug('connect to database')
    cursor = database_handling.connect_to_db(database)
    
    logger.bind(extra="import").debug('removing old jobs')
    sql = """DELETE FROM jobs; DELETE FROM registry; DELETE FROM schedule"""
    cursor.execute(sql, )
    

    for job in jobs.get('jobs',{}):
        task = job.get('job')
        description = job.get('description', task)
        preprocessing = job.get('preprocessing','')
        postprocessing = job.get('postprocessing', '')
        arguments = json.dumps(job.get('arguments',{}))
        schedule = job.get('schedule')

        sql = """INSERT INTO jobs (job, description, preprocessing, postprocessing, arguments) 
                 VALUES (%s, %s, %s, %s, %s) RETURNING id"""
        cursor.execute(sql, (task, description, preprocessing, postprocessing, arguments))
        job_id = cursor.fetchone()['id']

        sql = """INSERT INTO registry (job, schedule) VALUES (%s, %s) RETURNING id"""
        cursor.execute(sql, (job_id, schedule))
        registry_id = cursor.fetchone()['id']

        # commit data
        cursor.connection.commit()
