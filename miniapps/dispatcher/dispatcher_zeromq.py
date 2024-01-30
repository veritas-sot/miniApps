#!/usr/bin/env python

import sys
import zmq
import json
import psycopg2
import argparse
import os
import json
from loguru import logger
from veritas.tools import tools


class Dispatcher():

    def __init__(self, database=None):
        """init veritas dispatcher"""

        # database
        self._database = database
        self._db_connection = None
        self._cursor = None
        self._connect_to_db()

    def _connect_to_db(self):
        """connet to database"""
        logger.debug('connect to database')
        self._db_connection = psycopg2.connect(
                host=self._database['host'],
                database=self._database.get('database', 'journal'),
                user=self._database['user'],
                password=self._database['password'],
                port=self._database.get('port', 5432)
        )
        self._cursor = self._db_connection.cursor()

    def _extra_to_results(self, extra):
        try:
            data = json.loads(extra)
        except Exception as exc:
            logger.error(f'could not convert string to json; got exception {exc}')
            return

        print(json.dumps(data, indent=4))

    def _record_to_logs(self, appname, uuid, levelno, levelname, message, filename, 
                           pathname, lineno, module, function, functionname,
                           processname, threadname, exception, extra):

        sql = """INSERT INTO logs(app, uuid, levelno, levelname, message, filename, """ \
              """pathname, lineno, module, function, functionname, processname, threadname, exception, extra)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        self._cursor.execute(sql, (appname, 
                                   uuid, 
                                   levelno, 
                                   levelname, 
                                   message,
                                   filename,
                                   pathname, 
                                   lineno, 
                                   module, 
                                   function,
                                   functionname,
                                   processname,
                                   threadname,
                                   exception,
                                   extra))

        # commit the changes to the database
        self._db_connection.commit()

    def record_to_database(self, record):
            # write to database
            levelno = record.get('level',{}).get('no',-1)
            levelname = record.get('level',{}).get('name','')
            message = record.get('message',"")
            filename = record.get('file',{}).get('name','')
            pathname = record.get('file',{}).get('path','')
            lineno = record.get('line',0)
            module = record.get('module',"")
            function = record.get('function',"")
            functionname = record.get('name',"")
            processname = record.get('process',{}).get('name','')
            threadname = record.get('thread',{}).get('name','')
            exception = record.get('exception',"")
            uuid = record.get('extra',{}).get('uuid', None)
            if uuid:
                del record['extra']['uuid']
            extra = json.dumps(record.get('extra',""))

            appname = filename

            self._record_to_logs(appname, uuid, levelno, levelname, message, 
                                filename, pathname, lineno, module, function,
                                functionname,processname, threadname, 
                                exception,extra)
            self._extra_to_results(extra)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, default='dispatcher.yaml', required=False, help="used config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    dispatcher_config = tools.get_miniapp_config('messagebus', BASEDIR, args.config)
    if not dispatcher_config:
        print('unable to read config')
        sys.exit()

    zmq_protocol = dispatcher_config.get('zeromq',{}).get('protocol','tcp')
    zmq_host = dispatcher_config.get('zeromq',{}).get('host','127.0.0.1')
    zmq_port = dispatcher_config.get('zeromq',{}).get('port','12345')

    zmq_bind = f'{zmq_protocol}://{zmq_host}:{zmq_port}'
    socket = zmq.Context().socket(zmq.SUB)
    socket.bind(zmq_bind)
    socket.subscribe("")
    dispatcher = Dispatcher(database=dispatcher_config.get('database'))

    while True:
        _, message = socket.recv_multipart()
        print(message)
        # logger.debug(f'got message')
        # try:
        #     msg_decoded = message.decode("utf8").strip()
        #     msg_json = json.loads(msg_decoded)
        #     record = msg_json.get('record')
        #     dispatcher.record_to_database(record=record)
        # except Exception as exc:
        #     print('error')
        #     # logger.error(f'could not decode messagr {message}')