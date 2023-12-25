#!/usr/bin/env python

import getpass
import argparse
import os
from loguru import logger
from dotenv import load_dotenv, dotenv_values
from veritas.sot import sot

parser = argparse.ArgumentParser()
parser.add_argument('--set-salt', action='store_true')
parser.add_argument('--set-encryptionkey', action='store_true')
parser.add_argument('--set-iterations', action='store_true')

# Get the path to the directory this file is in
BASEDIR = os.path.abspath(os.path.dirname(__file__))
# Connect the path with the '.env' file name
load_dotenv(os.path.join(BASEDIR, '.env'))

# get SOT object
sot = sot.Sot()
args = parser.parse_args()

salt = getpass.getpass(prompt="Enter salt: ") if args.set_salt else os.getenv('SALT')
encryption_key = getpass.getpass(prompt="Enter encryptionkey: ") if args.set_encryptionkey else os.getenv('ENCRYPTIONKEY')
iterations = int(getpass.getpass(prompt="Enter iterations: ")) if args.set_iterations else os.getenv('ITERATIONS')

password = getpass.getpass(prompt="Enter password: ")
auth = sot.auth(salt=salt, encryption_key=encryption_key, iterations=int(iterations))
encrypted_password = auth.encrypt(password)
print(encrypted_password)