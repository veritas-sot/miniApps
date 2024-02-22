import json
import psycopg2
import pika
from psycopg2.extensions import AsIs
from loguru import logger

# veritas
from veritas import plugin
from . import abstract_dispatcher


class Dispatcher(abstract_dispatcher.Dispatcher):

    def __init__(self, config):
        """init dispatcher"""

        # set config for later use
        self._config = config

        # set database
        self._database = config.get('database', {})
        self._db_connection = None
        self._cursor = None

    def set_args(self, parser):
        parser.add_argument('--binding-keys', type=str, default="#", nargs="*", required=False, help="which logs to dispatch")
        parser.add_argument('--stdout', action='store_true', required=False, help="write to stdout instead to database")

    def start(self, args):
        """start dispatcher"""
        self._to_stdout = args.stdout

        logger.debug('connecting to database')
        self._connect_to_db()

        logger.debug('connecting to rabbitmq')
        self._binding_keys = args.binding_keys if args.binding_keys else ['#']

        connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
        channel = connection.channel()

        channel.exchange_declare(exchange='veritas_logs', exchange_type='topic')
        result = channel.queue_declare('', exclusive=True)
        queue_name = result.method.queue

        for binding_key in self._binding_keys:
            logger.debug(f'binding channel on {binding_key}')
            channel.queue_bind(exchange='veritas_logs', queue=queue_name, routing_key=binding_key)

        logger.info('starting rabbitmq consumer')
        channel.basic_consume(
            queue=queue_name, on_message_callback=self.get_message, auto_ack=True)

        channel.start_consuming()

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

    def _extra_to_results(self, uuid, result):
        """write results to database"""

        rcd_vals = {
            'uuid': uuid,
            'entity': result.get('details',{}).get('entity'),
            'message': result.get('details',{}).get('message'),
            'app': result.get('app')
        }
        columns = rcd_vals.keys()
        values = [rcd_vals[column] for column in columns]
        sql = 'INSERT INTO results (%s) values %s'
        try:
            self._cursor.execute(sql, (AsIs(','.join(columns)), tuple(values)))
        except Exception as exc:
            logger.error(f'could not add result {rcd_vals}; got exception {exc}')
        finally:
            self._db_connection.commit()

    def record_to_database(self, routing_key, record):
        """write log to database"""

        rcd_vals = {
            'date': record.get('time'),
            'app': record.get('app'),
            'levelno': record.get('level',{}).get('no',-1),
            'levelname': record.get('level',{}).get('name',''),
            'message': record.get('message',""),
            'filename': record.get('file',{}).get('name',''),
            'pathname': record.get('file',{}).get('path',''),
            'lineno': record.get('line',0),
            'module': record.get('module',""),
            'function': record.get('function',""),
            'functionname': record.get('name',""),
            'processname': record.get('process',{}).get('name',''),
            'threadname': record.get('thread',{}).get('name',''),
            'exception': record.get('exception',""),
            'uuid': record.get('uuid', None),
            'extra': json.dumps(record.get('extra',""))
        }

        columns = rcd_vals.keys()
        values = [rcd_vals[column] for column in columns]
        sql = 'INSERT INTO logs (%s) values %s'

        try:
            self._cursor.execute(sql, (AsIs(','.join(columns)), tuple(values)))
        except Exception as exc:
            logger.error(f'could not add result {rcd_vals}; got exception {exc}')
            return False

        if record.get('extra', {}).get('result'):
            # commit after extra 
            self._extra_to_results(
                record.get('uuid', None), 
                record.get('extra').get('result'))
        else:
            self._db_connection.commit()

        return True

    def get_message(self, ch, method, properties, body):
        routing_key = method.routing_key
        logger.debug(f'got message with routing_key {routing_key}')
        try:
            record = json.loads(body)
        except Exception as exc:
            logger.error(f'failed to load {body}; got exception {exc}')
            return
        if self._to_stdout:
            print(json.dumps(record, indent=4))
        else:
            self.record_to_database(routing_key, record)

@plugin.register('dispatcher')
def dispatch(config):
    """dispatch logs to database"""

    logger.info('dispatching logs to database or stdout')
    dispatcher = Dispatcher(config)
    return dispatcher
