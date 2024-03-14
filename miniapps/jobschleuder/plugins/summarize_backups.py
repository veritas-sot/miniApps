import database_handling
import os
import yaml
from loguru import logger

# veritas
from veritas.plugin import jobschleuder
from veritas.tools import tools


@jobschleuder("summarize_backups")
def summarize_backups(*args, **kwargs):

    # read config
    filename = './conf/summarize_backups.yaml'
    with open(filename) as f:
        logger.debug(f'reading config file: {filename}')
        local_config_file = yaml.safe_load(f.read())

    cursor = database_handling.connect_to_db(local_config_file.get('database'))

    period = kwargs.get('period','this_week')
    if period in ['today', 'this_week', 'last_week' ,'last_seven_days', 'this_month', 'this_year']:
        period = tools.get_date(period)
        sql = """SELECT device, last_attempt, last_success, status, message, EXTRACT(EPOCH FROM (last_attempt - last_success)) as delta
                FROM device_backups 
                WHERE last_attempt >= %s
        """
    else:
        sql = """SELECT device, last_attempt, last_success, status, message, EXTRACT(EPOCH FROM (last_attempt - last_success)) as delta
                FROM device_backups 
                WHERE last_attempt >= NOW() - INTERVAL %s
        """

    try:
        logger.debug(f'executing sql using period {period}')
        cursor.execute(sql, (period, ))
        rows = cursor.fetchall()
    except Exception as exc:
        logger.error(f'failed to get data from journals {exc}')
        return False

    # init empty response
    response = []

    for row in rows:
        device = row.get('device')
        last_attempt = row.get('last_attempt')
        last_success = row.get('last_success')
        status = row.get('status')
        message = row.get('message')
        delta = row.get('delta')
        details = {
            'device': device, 
            'last_attempt': last_attempt, 
            'last_success': last_success,
            'status': status,
            'message': message,
            'delta': delta}
        
        if int(abs(delta)) < 60:
            details.update({'status': 'OK'})
            logger.success(
                f'device: {device}, ' \
                f'last_attempt: {last_attempt}, ' \
                f'last_success: {last_success}, ' \
                f'status: {status}, ' \
                f'message: {message}, ' \
                f'delta: {delta}')
        else:
            details.update({'status': 'ERROR'})
            logger.error(
                f'device: {device}, ' \
                f'last_attempt: {last_attempt}, ' \
                f'last_success: {last_success}, ' \
                f'status: {status}, ' \
                f'message: {message}, ' \
                f'delta: {delta}')
        response.append(details)
