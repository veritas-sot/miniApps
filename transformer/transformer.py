#!/usr/bin/env python

import asyncio
import argparse
import json
import yaml
import urllib3
import sys
import jinja2
import re
import os
from loguru import logger
from veritas.tools import tools
from veritas.sot import sot as sot


if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    devicelist = []

    parser = argparse.ArgumentParser()

    parser.add_argument('--config', type=str, default="./transformer.yaml", required=False, help="transformer config file")
    # what devices
    parser.add_argument('--devices', type=str, default="", required=True, help="query to get list of devices")
    # what to transform
    parser.add_argument('--parameter', type=str, default="", required=True, help="which parameter to transform")
    # what to do
    parser.add_argument('--template', type=str, default="", required=False, help="template to use to transform value")
    parser.add_argument('--mapping', type=str, default="", required=False, help="mapping to use to transform value")
    parser.add_argument('--to-upper', action='store_true', required=False, help='transform string to upper case')
    parser.add_argument('--to-lower', action='store_true', required=False, help='transform string to lower case')
    parser.add_argument('--replace', type=str, default="", required=False, help="replace value eg. src/dst")
    parser.add_argument('--set', type=str, default="", required=False, help="set new value")
    # other paraneter
    parser.add_argument('--dry-run', action='store_true', required=False, help='print output but do no modification')
    parser.add_argument('--use-parent', action='store_true', required=False, help='use parent value')
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")
    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    # read config
    transformer_config = tools.get_miniapp_config('transformer', BASEDIR, args.config)
    if not transformer_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    tools.create_logger_environment(transformer_config, args.loglevel, args.loghandler)

    # we need the SOT object to talk to the SOT
    select = f'id,{args.parameter.split("__")[0]}'
    sot = sot.Sot(token=transformer_config['sot']['token'], url=transformer_config['sot']['nautobot'])
    devices = sot.select(select) \
                .using('nb.devices') \
                .where(args.devices)

    if args.mapping:
        # read file
        with open(args.mapping) as f:
            mapping = yaml.safe_load(f.read())

    for device in devices:
        logger.bind(extra=device.get('hostname','unset')).info('transforming device')
        id = device.get('id')
        old_value = tools.get_value_from_dict(device, args.parameter.split('__'))
        new_value = None

        # now transform value
        if args.to_upper:
            new_value = old_value.upper()
        elif args.to_lower:
            new_value = old_value.lower()
        elif args.replace:
            replacement = args.replace.split('/')
            new_value = old_value.replace(replacement[0], replacement[1])
        elif args.set:
            new_value = args.set
        elif args.mapping:
            if 'static' in mapping['mapping']:
                for key,value in mapping['mapping']['static'].items():
                    logger.bind(extra=device.get('hostname','unset')).debug(f'key: {key} value: {value}')
                    if old_value == key:
                        new_value = value
            elif 'regex' in mapping['mapping']:
                for regex, value in mapping['mapping']['regex'].items():
                    pattern = re.compile(regex)
                    match = pattern.match(old_value)
                    if match:
                        new_value = dict(value)
                        for k,v in value.items():
                            for group, group_val in match.groupdict().items():
                                if v == f'__{group}__':
                                    logger.bind(extra=device.get('hostname','unset')).debug(f'replacing {group} by {group_val}')
                                    new_value[k] = group_val
        elif args.template:
            # read template
            with open(args.template) as f:
                template = f.read()
            j2 = jinja2.Environment(loader=jinja2.BaseLoader, trim_blocks=False).from_string(template)
            try:
                new_value = j2.render({'values': device})
            except Exception as exc:
                logger.bind(extra=device.get('hostname','unset'))-error("could not render template; got exception: %s" % exc)
                continue

        # check if new_value is NOT none
        if not new_value:
            continue

        # build dict to update device
        update = {}
        if '__' in args.parameter:
            if args.use_parent:
                update[args.parameter.split('__')[0]] = new_value
            else:
                tools.set_value(update, args.parameter, new_value)
        else:
            update[args.parameter] = new_value

        nb_device = sot.get.device(id, by_id=True)
        if nb_device and len(update) > 0:
            if args.dry_run:
                print(f'[dry run] device: {nb_device.display} parameter: {args.parameter} ' \
                      f'old: {old_value} new: {new_value}')
            else:
                logger.bind(extra=device.get('hostname','unset')).debug(update)
                success = nb_device.update(update)
                if success:
                    logger.bind(extra=device.get('hostname','unset')).info(f'updated {nb_device.display} parameter: {args.parameter} ' \
                        f'old: {old_value} new: {new_value}')
                else:
                    logger.bind(extra=device.get('hostname','unset')).error(f'device not update {nb_device.display} parameter: {args.parameter} ' \
                        f'old: {old_value} new: {new_value}')
