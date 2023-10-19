#!/usr/bin/env python

import argparse
import logging
import os
import yaml
import json
import jinja2
import urllib3
from veritas.sot import sot as sot
from veritas.tools import tools

# set default config file to your needs
default_config_file = "./conf/smokeping.yaml"

if __name__ == "__main__":

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # init vars
    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--update', action='store_true', help='Update smpkeping config')
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="onboarding config file")
    # set the log level
    parser.add_argument('--loglevel', type=str, required=False, help="onboarding loglevel")

    # parse arguments
    args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    
    # read onboarding config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = default_config_file

    with open(config_file) as f:
        smokeping_config = yaml.safe_load(f.read())

    # set logging
    if args.loglevel is None:
        loglevel = tools.get_loglevel(tools.get_value_from_dict(smokeping_config, ['general', 'logging', 'level']))
    else:
        loglevel = tools.get_loglevel(args.loglevel)

    log_format = tools.get_value_from_dict(smokeping_config, ['general', 'logging', 'format'])
    if log_format is None:
        log_format = '%(asctime)s %(levelname)s:%(message)s'
    logfile = tools.get_value_from_dict(smokeping_config, ['general', 'logging', 'filename'])
    logging.basicConfig(level=loglevel, format=log_format)#, filename=logfile)

    # we need the SOT object to talk to the SOT
    sot = sot.Sot(token=smokeping_config['sot']['token'], 
                  url=smokeping_config['sot']['nautobot'],
                  ssl_verify=smokeping_config['sot'].get('ssl_verify', False))

    # for each target we query the data, parse the file and write the config to disk
    for target in smokeping_config.get('targets'):
        # the list of devices we process
        devices = []
        # this is the dict we are pasing to the jinja template
        # this dict comtains either the devices and the 'needed' values like custom fields or location
        unfiltered_values = {}
        values = {'devices': []}
        query_cfg = target.get('query',{})
        select = query_cfg.get('select')
        where = query_cfg.get('where')
        logging.debug(f'select {select} from nb.devices where {where}')
        unfiltered_values = sot.select(select) \
                               .using('nb.devices') \
                               .normalize(False) \
                               .where(where)

        # filter out devices with no primary IP address
        for device in unfiltered_values:
            # check if host has a primary ip
            if not device.get('primary_ip4') or \
                device.get('primary_ip4') == 'None' or \
                not device.get('primary_ip4',{}).get('address'):
                logging.error(f'host {device.get("hostname")} has no primary IP')
                continue
            values['devices'].append(device)

        # add static values to our dict
        static_values = target.get('static',{})
        for key,val in static_values.items():
            values[key] = val

        # loop through devices and write additional values to our dict
        for device in unfiltered_values:
            # we need the custom fields
            cf_data = device.get('custom_field_data')
            for key, val in cf_data.items():
                if key not in values:
                    values[key] = set()
                values[key].add(val)

            # and all the selected values
            for s in select.replace(' ','').split(','):
                vls = device.get(s)
                if isinstance(vls, dict):
                    if 'name' in vls:
                        if s not in values:
                            values[s] = set()
                        values[s].add(vls.get('name'))                        
                else:
                    values[s] = vls

        tmpl_name = target.get('template')
        template = smokeping_config.get('templates',{}).get(tmpl_name)

        j2 = jinja2.Environment(loader=jinja2.BaseLoader, trim_blocks=False).from_string(template)
        try:
            rendered = j2.render({'values': values})
            # now write file
            target = "%s/%s" % (smokeping_config.get('smokeping').get('configpath'),
                                target.get('filename'))
            logging.info(f'writing config to {target}')
            with open(target, "w") as f:
                f.write(rendered)
        except Exception as exc:
            logging.error("got exception: %s" % exc)
        
