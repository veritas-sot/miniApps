#!/usr/bin/env python

import argparse
import os
import sys
import getpass
import time
import asyncio
import netwalk
import yaml
from loguru import logger
from dotenv import load_dotenv, dotenv_values

import veritas.logging
from veritas.sot import sot
from veritas.tools import tools


BASEDIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_INDEX = "./conf/index.yaml"
OUTPUT_DIR = "./facts"
DEFAULT_THREADS = 2


if __name__ == "__main__":

    # defaults
    job = "reachability"
    walk = False
    write = False
    print_output = False
    commands = {}
    params = {}
    postfix = ""
    output_format = ""
    show_cdp = False

    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--seed', type=str, required=False)
    parser.add_argument('--device', type=str, required=False)
    parser.add_argument('--platform', type=str, default='ios')
    # the blacklist contains IP that are not used
    parser.add_argument('--blacklist', type=str, default='')
    parser.add_argument('--mapping', type=str, default='')
    # what todo
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--reachability', action='store_true')
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--job', type=str, required=False)
    # how to walk
    parser.add_argument('--no-walk-cdp', action='store_true')
    parser.add_argument('--walk-route', action='store_true')
    parser.add_argument('--walk-bgp', action='store_true')
    # output
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--print', action='store_true')
    parser.add_argument('--format', type=str, required=False)
    # we need username and password to connect to the device
    # credentials can be configured using a profile
    # have a look at the config file
    parser.add_argument('--username', type=str, required=False)
    parser.add_argument('--password', type=str, required=False)
    parser.add_argument('--profile', type=str, required=False)
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False)
    # dir to write collected data to
    parser.add_argument('--output', type=str, required=False)
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logger uuid")

    args = parser.parse_args()

    # check parameter
    if not args.seed and not args.device:
        print("Either seed (scanning) or device must be used")
        sys.exit()
    if args.seed:
        todo = "scan"
        walk = True
        starting_point = args.seed
    elif args.device:
        todo = "device"
        walk = False
        starting_point = args.device

    if args.output is None:
        output_dir = OUTPUT_DIR
    else:
        output_dir = args.output

    if args.reachability:
        job = "reachability"

    # check if .env file exists and read it
    if os.path.isfile(os.path.join(BASEDIR, '.env')):
        logger.debug(f'reading .env file')
        load_dotenv(os.path.join(BASEDIR, '.env'))
    else:
        logger.debug(f'no .env file found; trying to read local crypto parameter')
        crypt_parameter = tools.get_miniapp_config('onboarding', BASEDIR, "salt.yaml")
        os.environ['ENCRYPTIONKEY'] = crypt_parameter.get('crypto', {}).get('encryptionkey')
        os.environ['SALT'] = crypt_parameter.get('crypto', {}).get('salt')
        os.environ['ITERATIONS'] = str(crypt_parameter.get('crypto', {}).get('iterations'))

    # read config
    nachtwaechter_config = tools.get_miniapp_config('nachtwaechter', BASEDIR, args.config)
    if not nachtwaechter_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=nachtwaechter_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='kobold',
        uuid=args.uuid)

    # we just need the tools
    sot = sot.Sot(token="", url="")

    # get username and password either from profile
    username, password = tools.get_username_and_password(
        profile_config,
        args.profile,
        args.username,
        args.password)

    # set some parameter
    if args.baseline:
        job = "baseline"
    elif args.reachability:
        job = "reachability"
    elif args.inventory:
        job = "inventory"
    else:
        if not args.job:
            print("no job specified")
            sys.exit()
        job = args.job

    # read job and postfix
    if job not in nachtwaechter_config['jobs']:
        print("Unknown job %s" % job)
        sys.exit()

    # template_index = utilities.read_config(TEMPLATES_INDEX)['index']
    with open(TEMPLATES_INDEX) as f:
        template_index = yaml.safe_load(f.read())['index']

    job_config = nachtwaechter_config['jobs'][job]
    postfix = job_config.get('postfix')
    output_format = job_config.get('format', 'json')
    # overwrite format if user want a different one
    if args.format:
        output_format = args.format

    if 'join' in job_config:
        params.update({'join': job_config['join']})
    for line in job_config['commands']:
        if line['command'] == "echo":
            commands['echo'] = 'echo'
        else:
            for index in template_index:
                if index['command'] == line['command']:
                    commands[index['command']] = index
                if line['command'] == "show cdp neighbors detail":
                    show_cdp = True

    if walk:
        if not args.no_walk_cdp:
            commands.update ({"show cdp neighbors detail": {
                "command": "show cdp neighbors detail",
                "template": {
                    "ios": "cisco_ios_show_cdp_neighbors_detail.textfsm",
                    "nxos": "cisco_nxos_show_cdp_neighbors_detail.textfsm"
                }
            }})
        if args.walk_route:
            commands.update ({"show ip route": {
                "command": "show ip route",
                "template": {
                    "ios": "cisco_ios_show_ip_route.textfsm",
                    "nxos": "cisco_nxos_show_ip_route.textfsm"
                }
            }})
        if args.walk_bgp:
            commands.update ({"show ip bgp neighbors": {
                "command": "show ip bgp neighbors",
                "template": {
                    "ios": "cisco_ios_show_ip_bgp_neighbors.textfsm",
                    "nxos": "cisco_nxos_show_ip_bgp_neighbors.textfsm"
                }
            }})

    # set number of parallel tasks
    threads = nachtwaechter_config.get('nachtwaechter',{}).get('threads')
    threads = DEFAULT_THREADS if not threads else threads

    # read blacklist
    if args.blacklist:
        if os.path.isfile(BASEDIR + "/conf/%s" % args.blacklist):
            with open(BASEDIR + "/conf/%s" % args.blacklist, "r") as filehandler:
                hosts = filehandler.read().splitlines()
                for h in hosts:
                    blacklisted_hosts.add(h)
        else:
            print("blacklist %s configured but not found" % (BASEDIR + "/conf/%s" % args.blacklist))

    # read mapping
    if args.mapping:
        if os.path.isfile(BASEDIR + "/conf/%s" % args.mapping):
            # mappings_config = utilities.read_config(BASEDIR + "/conf/%s" % args.mapping)
            with open(BASEDIR + "/conf/%s" % args.mapping, "r") as filehandler:
                 with open(BASEDIR + "/conf/%s" % args.mapping) as f:
                    mappings_config = yaml.safe_load(f.read())
            # print(json.dumps(mappings_config['mappings'], indent=4))
            for mapping in mappings_config['mappings']:
                # print(mapping)
                mappings[mapping['mapping']['src']] = mapping['mapping']['dest']
        else:
            print("mapping configured but not found")

    params.update({
        'started': time.time(),
        'threads': threads,
        'auth_username': username,
        'auth_password': password,
        'output': output_dir,
        'commands': commands, # hier die gesamte konfig des teils
        'job': job,
        'postfix': postfix,
        'todo': todo,
        'walk': walk,
        'write': args.write,
        'print': args.print,
        'format': output_format,
        'show_cdp': show_cdp
    })

    # print(json.dumps(params, indent=4))
    netwalk = netwalk.Netwalk(seed={'host_ip': starting_point, 'hostname': 'seed', 'platform': args.platform},
                              params=params)
    asyncio.run(netwalk.run())
