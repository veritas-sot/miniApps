#!/usr/bin/env python

import argparse
import os
import smtplib
import pandas as pd
from loguru import logger
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import veritas.logging
from veritas.journal import journal
from veritas.tools import tools
from veritas.sot import sot as veritas_sot
    

def activities(jrnl, smtp_config, opened=None, closed=None, status=None, cols=None):


    logger.debug(f'get uuids between {opened} and {closed} having status {status}')
    uuids = jrnl.get_journals(opened_gt=opened,
                              closed_gt=closed,
                              status=status)

    # Create a MIMEMultipart class, and set up the From, To, Subject fields
    email_message = MIMEMultipart()
    email_message['From'] = smtp_config.get('from')
    email_message['To'] = smtp_config.get('to')
    email_message['Subject'] = 'Report'
    
    body = f'Activities between {opened} and {closed} having status {status}'

    for row in uuids:
        uuid = row.get('journal_uuid')
        logger.debug(f'uuid {uuid}')
        activities = jrnl.get_activities(uuid=uuid)
        messages = jrnl.get_messages(uuid=uuid)

        if activities:
            df = pd.DataFrame(activities)
            activities_html = df.to_html(header=True, index=True)
            email_message.attach(MIMEText(activities_html, 'html'))
        
        if messages:
            df = pd.DataFrame(messages)
            messages_html = df.to_html(header=True, index=True)
            email_message.attach(MIMEText(messages_html, 'html'))

        if cols:
            for activity in activities:
                activity_uuid = activity.get('activity_uuid')
                activity_name = activity.get('activity')
                if activity_uuid:
                    logs = jrnl.get_logs(uuid=activity_uuid, cols=cols)
                    if logs:
                        df = pd.DataFrame(logs)
                        logs_html = df.to_html(header=True, index=True)
                        email_message.attach(MIMEText(logs_html, 'html'))

    # Define the HTML document
    html = '''
        <html>
            <body>
                <h1>Weeky report of your activities</h1>
                <p>Hello, welcome to your report!</p>
            </body>
        </html>
        '''

    # add mime
    email_message.attach(MIMEText(body, 'plain'))
    tools.write_mail(email_message, smtp_config)

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, default='report.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # use uuid if you want a report for this uuid only
    parser.add_argument('--uuid', type=str, required=False, help="specific journal uuid")
    # use a range to create a report of multiple journals
    parser.add_argument('--opened', type=str, required=False, help="journals that were opened after this date")
    parser.add_argument('--closed', type=str, required=False, help="journals that were closed after this date")
    parser.add_argument('--status', type=str, required=False, help="either active or closed")
    # what kind of report
    parser.add_argument('--activities', action='store_true', help='report activities')
    # logs
    parser.add_argument('--logs', type=str, required=False, help="add logs of journal")
    parser.add_argument('--all', action='store_true', help='add full details')
    parser.add_argument('--extra', action='store_true', help='add extra column (logs)')
    parser.add_argument('--cols', type=str, required=False, help='add list of columns (logs)')

    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    report_config_file = tools.get_miniapp_config('report.yaml', BASEDIR, args.config)
    if not report_config_file:
        print('unable to read config')
        return

    # create logger environment
    veritas.logging.create_logger_environment(
        config=report_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='report',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=report_config_file['sot']['token'], 
                          url=report_config_file['sot']['nautobot'],
                          ssl_verify=report_config_file['sot'].get('ssl_verify', False))

    # get journal instance
    jrnl = journal.Journal()

    cols = None
    if args.logs:
        if args.all:
            cols = ['*']
        elif args.cols:
            cols = args.cols.split(',')
        elif args.extra:
            cols = ['id', 'app', 'date', 'levelname', 'module', 'message', 'extra']
        else:
            cols = ['id', 'app', 'date', 'levelname', 'module', 'message']

    if args.activities:

        if args.opened in ['today', 'this_week', 'last_week',
                            'last_seven_days', 'this_month']:
            opened = tools.get_date(args.opened) 
        else:
             opened = args.opened
        
        if args.closed in ['today', 'this_week', 'last_week',
                            'last_seven_days', 'this_month']:
            closed = tools.get_date(args.closed) 
        else:
             closed = args.closed

        activities(jrnl, 
                   report_config_file.get('general',{}).get('smtp'), 
                   opened=opened, 
                   closed=closed, 
                   status=args.status,
                   cols=cols)


if __name__ == "__main__":
    main()
