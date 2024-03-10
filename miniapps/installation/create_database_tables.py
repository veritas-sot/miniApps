#!/usr/bin/env python

import yaml
import psycopg2
import psycopg2.extras
import argparse


def main():

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='database_tables.yaml', required=False, help="database config file")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f.read())

    for job in config.get('jobs',{}):
        database = job.get('database')
        tables = job.get('tables','').replace(' ','')
        conn, cursor = connect_to_db(database)
        for table in tables.split(','):
            print(table)
            cursor.execute(config.get(table), )
        conn.commit()

def connect_to_db(database):
    conn = psycopg2.connect(
            host=database['host'],
            database=database.get('database'),
            user=database['username'],
            password=database['password'],
            port=database.get('port', 5432)
    )
    return conn, conn.cursor(cursor_factory = psycopg2.extras.RealDictCursor)


if __name__ == "__main__":
    main()