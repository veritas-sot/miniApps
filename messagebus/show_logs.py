#!/usr/bin/env python

import sys
import zmq
from loguru import logger

socket = zmq.Context().socket(zmq.SUB)
socket.bind("tcp://127.0.0.1:12345")
socket.subscribe("")

logger.configure(handlers=[{"sink": sys.stderr, "format": "{message}"}])

while True:
    _, message = socket.recv_multipart()
    logger.info(message.decode("utf8").strip())
