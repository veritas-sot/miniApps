import yaml
import json
import os
import glob
import re
from loguru import logger
from collections import defaultdict
from veritas.sot import sot as sot
from businesslogic import your_config_context as user_cc
from ttp import ttp


def to_sot(sot, args, device_fqdn, configparser, device_defaults, onboarding_config):
    device_context = {}

    standard_config_context(device_fqdn,
                            device_context,
                            configparser,
                            device_defaults,
                            onboarding_config)

    # call the user defined business logic
    # the user defined bl can overwrite and modify the device_context
    user_cc.config_context(device_fqdn,
                           device_context,
                           configparser,
                           onboarding_config)

    # print(json.dumps(device_context, indent=4))
    # because our device_context is NOT a dict but a default_dict of default_dicts
    # we have to convert our context to a string, then json and then yaml
    # complicated, maybe there is a better way but it works
    device_context_string = json.dumps(device_context[device_fqdn])
    device_context_json = json.loads(device_context_string)
    device_context_yaml = yaml.dump(device_context_json,
                                    allow_unicode=True,
                                    default_flow_style=False)

    if args.write_hldm or args.show_hldm:
        return device_context

    config = {
        'repo': 'config_contexts',
        'filename': "%s.yml" % device_fqdn,
        'subdir': "devices",
        'content': "%s\n%s" % ("---", device_context_yaml),
        'action': 'overwrite',
        'pull': False,
    }

    logger.info("writing config_context to sot")
    sot.device(device_fqdn).set_config_context(config)

    return device_context

def standard_config_context(device_fqdn, device_context, configparser, device_defaults, onboarding_config):

    basedir = "%s/%s" % (onboarding_config.get('git').get('app_configs').get('path'),
                         onboarding_config.get('git').get('app_configs').get('subdir'))
    directory = os.path.join(basedir, './config_context/')
    files = []

    # we read all *.yaml files in our config_context config dir
    for filename in glob.glob(os.path.join(directory, "*.yaml")):
        with open(filename) as f:
            logger.debug("opening file %s to read config_context config" % filename)
            try:
                config = yaml.safe_load(f.read())
                if config is None:
                    logger.error("could not parse file %s" % filename)
                    continue
            except Exception as exc:
                logger.error("could not read file %s; got exception %s" % (filename, exc))
                continue

            name = config.get('name','error_please_fix_it')
            platform = config.get('platform')
            if not config.get('active'):
                logger.debug("config context %s in %s is not active" % (name, filename))
                continue
            if platform is not None:
                if platform != 'all' and platform != device_defaults["platform"]:
                    logger.debug("skipping config context %s wrong platform %s" % (name, platform))
                    continue

            logger.info("processing context %s in %s" % (name, filename))
            # add filename to our list of files that were processed
            files.append(os.path.basename(filename))

            # get the source. It is either a section or a (named) regular expression
            if 'section' in config['source']:
                logger.debug(f'found section in config')
                device_config_as_list = configparser.get_section(config['source']['section'])
                device_config = "\n".join(device_config_as_list)
            elif 'fullconfig' in config['source']:
                logger.debug(f'found fullconfig in config')
                device_config = configparser.get()
            else:
                logger.error("unknown source %s" % config['source'])
                continue

            if len(device_config) == 0:
                logger.error("no device config with configured pattern found")
                continue

            dc = parse_config(device_config, config)
            if device_fqdn not in device_context:
                device_context[device_fqdn] = {}
            device_context[device_fqdn][name] = dc

def stripper(data):
    # remove keys with empty values
    new_data = {}
    for k, v in data.items():
        if isinstance(v, dict):
            v = stripper(v)
        if not v in (u'', None, {}):
            new_data[k] = v
    return new_data

def parse_config(device_config, config):
    # get template
    ttp_template = config.get('template')
    if ttp_template is None:
        logger.error('no template found')
        return None

    # create parser object and parse data using template:
    parser = ttp(data=device_config, template=ttp_template)
    parser.parse()
    parsed_config = parser.result(format='raw')[0]
    if 'remove_empty' in config:
        return stripper(parsed_config[0])
    else:
        return parsed_config[0]