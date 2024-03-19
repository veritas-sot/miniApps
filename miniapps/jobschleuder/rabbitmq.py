import pika
from loguru import logger


def open_rabbitmq(rabbitmq_config:str):
    rabbitmq_host = rabbitmq_config.get('host', 'localhost')
    rabbitmq_port = rabbitmq_config.get('port', 5672)
    rabbitmq_queue = rabbitmq_config.get('queue')
    rabbitmq_user = rabbitmq_config.get('user')
    rabbitmq_password = rabbitmq_config.get('password')
    rabbitmq_heartbeat = rabbitmq_config.get('heartbeat',60)
    rabbitmq_blocked_connection_timeout = rabbitmq_config.get('blocked_connection_timeout', 600)

    if rabbitmq_user and rabbitmq_password:
        parameter = pika.ConnectionParameters(
            host=rabbitmq_host, 
            port=rabbitmq_port,
            heartbeat=rabbitmq_heartbeat,
            blocked_connection_timeout=rabbitmq_blocked_connection_timeout,
            credentials=pika.PlainCredentials(rabbitmq_user, rabbitmq_password))
    else:
        parameter = pika.ConnectionParameters(
            host=rabbitmq_host, 
            port=rabbitmq_port,
            heartbeat=rabbitmq_heartbeat,
            blocked_connection_timeout=rabbitmq_blocked_connection_timeout)

    logger.bind(extra="rabbitmq").info(f'rabbit: {rabbitmq_host}:{rabbitmq_port} queue: {rabbitmq_queue}')

    connection = pika.BlockingConnection(parameter)
    channel = connection.channel()
    channel.queue_declare(queue=rabbitmq_queue, durable=True)

    return channel, rabbitmq_queue

def get_message_count(channel, queue):
    status = channel.queue_declare(queue, passive=True)
    return status.method.message_count

