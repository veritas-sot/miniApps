#!/usr/bin/env python

import argparse
import pandas as pd
from loguru import logger
from rich.console import Console as RichConsole
from rich.table import Table as RichTable
from veritas.journal import journal


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

def list_journals(jrnl):

    active_journals = jrnl.get_active_journals(status='active')
    df = pd.DataFrame(active_journals)
    print_table(df=df, title='Active Journals')

def show_journal(jrnl, uuid, show_logs=False):
    """print tables containing activities, messages, and logs"""
    activities = jrnl.get_activities(uuid=uuid)
    messages = jrnl.get_messages(uuid=uuid)

    if activities:
        df = pd.DataFrame(activities)
        print_table(df=df, title='Activities')
    
    if messages:
        df = pd.DataFrame(messages)
        print_table(df=df, title='Messages')
    
    if show_logs:
        cols = ['id', 'app', 'date', 'levelname', 'module', 'message']
        for activity in activities:
            activity_uuid = activity.get('activity_uuid')
            activity_name = activity.get('activity')
            if activity_uuid:
                logs = jrnl.get_logs(uuid=activity_uuid, cols=cols)
                if logs:
                    df = pd.DataFrame(logs)
                    print_table(df=df, title=f'Logs {activity_name} ({activity_uuid})')

def show_logs(jrnl, uuid, cols):

    logs = jrnl.get_logs(uuid=uuid, cols=cols)
    if logs:
        df = pd.DataFrame(logs)
        print_table(df=df, title='Logs')
    else:
        logger.error('got no data from database')

def close(jrnl, uuid):
    jrnl.close(uuid=uuid)

# def report(jrnl, uuid):

#     activities = jrnl.get_activities(uuid=uuid)
#     messages = jrnl.get_messages(uuid=uuid)
#     logs_df = []

#     if activities:
#         activities_df = pd.DataFrame(activities)

#     if messages:
#         messages_df = pd.DataFrame(messages)

#     cols = ['id', 'app', 'date', 'levelname', 'module', 'message']
#     for activity in activities:
#         activity_uuid = activity.get('activity_uuid')
#         activity_name = activity.get('activity')
#         if activity_uuid:
#             logs = jrnl.get_logs(uuid=activity_uuid, cols=cols)
#             if logs:
#                 logs.append(pd.DataFrame(logs))

#     html = activities_df.to_html(header=True, index=True)
#     # write_email(html)

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--close', type=str, required=False, help='close journal')
    parser.add_argument('--report', type=str, required=False, help='report journal')
    parser.add_argument('--list', action='store_true', help='list all open kournals')
    parser.add_argument('--loglevel', type=str, required=False, default="INFO", help="used loglevel")
    parser.add_argument('--journal', type=str, required=False, help="show details of journal")
    parser.add_argument('--logs', type=str, required=False, help="show logs of journal")
    parser.add_argument('--all', action='store_true', help='show full details')
    parser.add_argument('--extra', action='store_true', help='show extra column (logs)')
    parser.add_argument('--cols', type=str, required=False, help='list of columns (logs)')
    parser.add_argument('--show-logs', action='store_true', help='show logs (journal details)')

    args = parser.parse_args()

    # get journal instance
    jrnl = journal.Journal()

    if args.close:
        close(jrnl, uuid=args.close)
    if args.list:
        list_journals(jrnl=jrnl)
    if args.journal:
        show_journal(jrnl=jrnl, uuid=args.journal, show_logs=args.show_logs)
    # if args.report:
    #     report(jrnl=jrnl, uuid=args.report)
    if args.logs:
        if args.all:
            cols = ['*']
        elif args.cols:
            cols = args.cols.split(',')
        elif args.extra:
            cols = ['id', 'app', 'date', 'levelname', 'module', 'message', 'extra']
        else:
            cols = ['id', 'app', 'date', 'levelname', 'module', 'message']
        show_logs(jrnl=jrnl, uuid=args.logs, cols=cols)

if __name__ == "__main__":
    main()
