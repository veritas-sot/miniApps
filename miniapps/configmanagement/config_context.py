import os
import glob
import yaml
import json
from loguru import logger
from ttp import ttp


def get_config_context(task, cm, device_config:dict, template_dir:str, device_platform:str="ios",):

    device_fqdn = task.host
    logger.debug(f'getting config context for {device_fqdn} from {template_dir}/{task.host.platform}')
    device_context = {}
    standard_config_context(
        cm,
        device_fqdn,
        device_context,
        device_config,
        device_platform,
        f'{template_dir}/{task.host.platform}')
    return device_context

def standard_config_context(cm, device_fqdn, device_context, device_config, device_platform, template_dir):

    files = []

    # we read all *.yaml files in our config_context config dir
    for filename in glob.glob(os.path.join(template_dir, "*.yaml")):
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
                if platform != 'all' and platform != device_platform:
                    logger.debug("skipping config context %s wrong platform %s" % (name, platform))
                    continue

            logger.info("processing context %s in %s" % (name, filename))
            # add filename to our list of files that were processed
            files.append(os.path.basename(filename))

            # get the source. It is either a section or a (named) regular expression
            if 'section' in config['source']:
                logger.debug('found section in config')
                device_config_as_list = cm.get_section(device_config, config['source']['section'])
                device_config = "\n".join(device_config_as_list)
            elif 'fullconfig' in config['source']:
                logger.debug('found fullconfig in config')
            else:
                logger.error("unknown source %s" % config['source'])
                continue

            if len(device_config) == 0:
                logger.error("no device config with configured pattern found")
                continue

            dc = parse_config(device_config, config)
            device_context.update(dc)

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
    return parsed_config[0]

def set_device_config_context(task, cm, sot, update_context, device_context):
    device_fqdn = task.host
    if update_context:
        # merge the existing context with the new context
        try:
            existing_context = task.host['config_context']
            if existing_context is not None:
                device_context = {**existing_context, **device_context}
            logger.debug('updating device context')
            print(json.dumps(device_context, indent=4))
            return sot.device(str(task.host)).update({'local_config_context_data': device_context})
        except Exception as exc:
            logger.bind(extra="context").error(f'failed to update config context; got {exc}')
    else:
        logger.debug(f'setting device context for {device_fqdn}')
        print(json.dumps(device_context, indent=4))
        return sot.device(str(task.host)).update({'local_config_context_data': device_context})
