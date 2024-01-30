#!/usr/bin/env python

import argparse
import os
import jinja2
import urllib3
import sys
from loguru import logger

# veritas
import veritas.logging
from veritas.sot import sot as veritas_sot
from veritas.tools import tools


def main(args_list=None):

    # to disable warning if TLS warning is written to console
    urllib3.disable_warnings()

    # init vars
    parser = argparse.ArgumentParser()
    # what to do
    parser.add_argument('--update', action='store_true', help='Update smpkeping config')
    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False, help="onboarding config file")
    # set the log level and handler
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    # uuid is written to the database logger
    parser.add_argument('--uuid', type=str, required=False, help="database logging uuid")

    # parse arguments
    if args_list:
        args = parser.parse_args(args_list)
    else:
        args = parser.parse_args()

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    
    # read config
    smokeping_config = tools.get_miniapp_config('sync_smokeping', BASEDIR, args.config)
    if not smokeping_config:
        print('unable to read config')
        sys.exit()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=smokeping_config, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='sync_phpipam',
        uuid=args.uuid)

    # we need the SOT object to talk to the SOT
    sot = veritas_sot.Sot(token=smokeping_config['sot']['token'], 
                          url=smokeping_config['sot']['nautobot'],
                          ssl_verify=smokeping_config['sot'].get('ssl_verify', False),
                          debug=False)

    # for each target we query the data, parse the file and write the config to disk
    for target in smokeping_config.get('targets'):
        # this is the dict we are passing to the jinja template
        # this dict contains the devices and the 'needed' values like custom fields or location
        unfiltered_values = {}
        values = {'devices': []}
        query_cfg = target.get('query',{})
        select = query_cfg.get('select')
        where = query_cfg.get('where')
        logger.debug(f'select {select} from nb.devices where {where}')
        unfiltered_values = sot.select(select) \
                               .using('nb.devices') \
                               .where(where)
        # print(json.dumps(unfiltered_values, indent=4))
        # filter out devices with no primary IP address
        for device in unfiltered_values:
            # check if host has a primary ip
            if not device.get('primary_ip4') or \
                device.get('primary_ip4') == 'None' or \
                not device.get('primary_ip4',{}).get('address'):
                logger.error(f'host {device.get("hostname")} has no primary IP')
                continue
            values['devices'].append(device)

        # add static values to our dict
        static_values = target.get('static',{})
        for key,val in static_values.items():
            values[key] = val

        # loop through devices and write additional values to our dict
        for device in unfiltered_values:
            # we need the custom fields
            cf_data = device.get('custom_field_data', device.get('_custom_field_data',{}))
            for key, val in cf_data.items():
                if key not in values:
                    values[key] = set()
                values[key].add(val)
                # logger.debug(f'adding {key}={val}')

            # and all the selected values
            for s in select.replace(' ','').split(','):
                vls = device.get(s)
                if isinstance(vls, dict):
                    if 'name' in vls:
                        if s not in values:
                            values[s] = set()
                        values[s].add(vls.get('name'))     
                        # logger.debug(f'adding {s}={vls.get("name")}')          
                else:
                    values[s] = vls
                    # logger.debug(f'adding {s}={vls}')

        tmpl_name = target.get('template')
        template = smokeping_config.get('templates',{}).get(tmpl_name)

        j2 = jinja2.Environment(loader=jinja2.BaseLoader, trim_blocks=False).from_string(template)
        try:
            rendered = j2.render({'values': values})
            # now write file
            target = "%s/%s" % (smokeping_config.get('smokeping').get('configpath'),
                                target.get('filename'))
            logger.info(f'writing config to {target}')
            with open(target, "w") as f:
                f.write(rendered)
        except Exception as exc:
            logger.error("got exception: %s" % exc)
        
if __name__ == "__main__":
    """main entry point

    it is possible to use this script without a cli. 

    import sys
    sys.path.append('../sync_smokeping)
    import sync_backup as sync_backup

    sync_backup.main(['--loglevel', 'info',
                      '--uuid', uuid,
                      '--update', ''])

    """
    main()
