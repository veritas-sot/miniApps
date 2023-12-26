import yaml
import os
import glob
from loguru import logger
from veritas.sot import sot as sot


def to_sot(sot, conn, device_facts, device_defaults, onboarding_config):
    basedir = "%s/%s" % (onboarding_config.get('git').get('app_configs').get('path'),
                         onboarding_config.get('git').get('app_configs').get('subdir'))
    directory = os.path.join(basedir, './cables/')
    files = []

    for filename in glob.glob(os.path.join(directory, "*.yaml")):
        with open(filename) as f:
            logger.debug("opening file %s to read facts config" % filename)
            try:
                config = yaml.safe_load(f.read())
                if config is None:
                    logger.error("could not parse file %s" % filename)
                    continue
            except Exception as exc:
                logger.error("could not read file %s; got exception %s" % (filename, exc))
                continue

            active = config.get('active')
            name = config.get('name')
            if not active:
                logger.debug("config context %s in %s is not active" % (name, filename))
                continue

            file_vendor = config.get("vendor")
            if file_vendor is None or file_vendor != device_defaults["manufacturer"]:
                logger.debug("skipping file %s (%s)" % (filename, file_vendor))
                continue

            files.append(os.path.basename(filename))            
            values = conn.send_and_parse_command(commands=gconfig['cables'])

            first_command = config['cables'][0]['command']['cmd']
            for value in values[first_command]:
                connection = {"side_a": device_facts['fqdn'],
                              "side_b": value['DESTINATION_HOST'],
                              "interface_a": value['LOCAL_PORT'],
                              "interface_b": value['REMOTE_PORT'],
                              "cable_type": "cat5e"
                              }
                newconfig = {
                    "name": device_facts['fqdn'],
                    "config": connection
                }
                logger.info("sendnig request to add cable (%s - %s) to sot" % (value['LOCAL_PORT'], value['REMOTE_PORT']))
                success = sot.device(device_facts['fqdn']) \
                            .interface(value['LOCAL_PORT']) \
                            .connection_to(device=value['DESTINATION_HOST'], interface=value['REMOTE_PORT'])

    # result[device_facts["fqdn"]]['cable'] = "Processing cables %s" % files
