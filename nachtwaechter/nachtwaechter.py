#!/usr/bin/env python

import argparse
import logging
import os
import sys
import getpass
import time
import asyncio
import netwalk
from dotenv import load_dotenv, dotenv_values
from veritas.tools import tools


BASEDIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_CONFIG_FILE = "./conf/nachtwaechter.yaml"
TEMPLATES_INDEX = "./conf/index.yaml"
OUTPUT_DIR = "./facts"
DEFAULT_THREADS = 2


if __name__ == "__main__":

    # defaults
    profile = "reachability"
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
    parser.add_argument('--commands', type=str, required=False)
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
        profile = "reachability"

    # Connect the path with the '.env' file name
    load_dotenv(os.path.join(BASEDIR, '.env'))
    # you can get the env variable by using var = os.getenv('varname')

    # read nachtwaechter config
    config_file = args.config if args.config is not None else DEFAULT_CONFIG_FILE
    with open(config_file) as f:
        nachtwaechter_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(nachtwaechter_config, ['general', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(nachtwaechter_config, ['general', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(nachtwaechter_config, ['general', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)

    # get username and password from profile if user configured args.profile
    if args.profile is not None:
        username = nachtwaechter_config.get('profiles',{}).get(args.profile,{}).get('username')
        token = nachtwaechter_config.get('profiles',{}).get(args.profile,{}).get('password')
        auth = sot.auth(encryption_key=os.getenv('ENCRYPTIONKEY'), 
                        salt=os.getenv('SALT'), 
                        iterations=int(os.getenv('ITERATIONS')))
        password = auth.decrypt(token)

    # overwrite username and password if configured by user
    username = args.username if args.username else username
    password = args.password if args.password else password

    username = input("Username (%s): " % getpass.getuser()) if not username else username
    password = getpass.getpass(prompt="Enter password for %s: " % username) if not password else password

    # set some parameter
    if args.baseline:
        profile = "baseline"
    elif args.reachability:
        profile = "reachability"
    elif args.inventory:
        profile = "inventory"
    else:
        if not args.commands:
            print("no profile specified")
            sys.exit()
        profile = args.commands

    # read profile and postfix
    if profile not in nachtwaechter_config['profiles']:
        print("Unknown profile %s" % profile)
        sys.exit()

    # template_index = utilities.read_config(TEMPLATES_INDEX)['index']
    with open(TEMPLATES_INDEX) as f:
        template_index = yaml.safe_load(f.read())['index']

    profile_config = nachtwaechter_config['profiles'][profile]
    postfix = profile_config.get('postfix')
    output_format = profile_config.get('format', 'json')
    # overwrite format if user want a different one
    if args.format:
        output_format = args.format

    if 'join' in profile_config:
        params.update({'join': profile_config['join']})
    for line in profile_config['commands']:
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
    if 'threads' in nachtwaechter_config['nachtwaechter']:
        threads = nachtwaechter_config['nachtwaechter']['threads']
    else:
        threads = DEFAULT_THREADS

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
        'profile': profile,
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
