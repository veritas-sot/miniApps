#!/usr/bin/env python

import getpass
import argparse
import os
from dotenv import load_dotenv

# veritas
import veritas.auth

parser = argparse.ArgumentParser()
parser.add_argument('--salt', type=str)
parser.add_argument('--encryptionkey', type=str)
parser.add_argument('--iterations', type=str)

# Get the path to the directory this file is in
BASEDIR = os.path.abspath(os.path.dirname(__file__))

if os.path.isfile(os.path.join(BASEDIR, '.env')):
    load_dotenv(os.path.join(BASEDIR, '.env'))

# get SOT object
args = parser.parse_args()

salt = args.salt if args.salt else os.environ['SALT']
encryption_key = args.encryptionkey if args.encryptionkey else os.environ['ENCRYPTIONKEY']
iterations = args.iterations if args.iterations else  os.environ['ITERATIONS']

password = getpass.getpass(prompt="Enter password: ")
encrypted_password = veritas.auth.encrypt(password=password, 
                                          salt=salt, 
                                          encryption_key=encryption_key, 
                                          iterations=int(iterations))
print(encrypted_password)
