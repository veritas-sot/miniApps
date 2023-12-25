#!/usr/bin/env python

import argparse
import os
import yaml
import jinja2
import csv
import sys
from loguru import logger


BASEDIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_CONFIG_FILE = "./convert_csv.yaml"


if __name__ == "__main__":

    config = None
    overall_values = []

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--config', type=str, required=False)
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)

    args = parser.parse_args()

   # read csv2yaml config
    if args.config is not None:
        config_file = args.config
    else:
        config_file = DEFAULT_CONFIG_FILE

    logger.basicConfig(level=logger.DEBUG,
                        format="%(levelname)s - %(message)s")
    # read config
    with open(config_file) as f:
        config = yaml.safe_load(f.read())

    mappings = config.get('mappings')
    filename = args.input
    delimiter = config['defaults'].get('delimiter',',')
    quotechar = config['defaults'].get('quotechar','|')
    quoting_cf = config['defaults'].get('quoting','minimal')
    newline = config['defaults'].get('newline','')
    if quoting_cf == "none":
        quoting = csv.QUOTE_NONE
    elif quoting_cf == "all":
        quoting = csv.QUOTE_ALL
    elif quoting_cf == "nonnumeric":
        quoting = csv.QUOTE_NONNUMERIC
    else:
        quoting = csv.QUOTE_MINIMAL
    logger.info(f'reading {filename} delimiter={delimiter} quotechar={quotechar} newline={newline} quoting={quoting_cf}')

    # read CSV file
    with open(filename, newline=newline) as csvfile:
        overall_values = []
        output = ""
        csv_vals = csv.DictReader(csvfile, 
                                  delimiter=delimiter, 
                                  quoting=quoting,
                                  quotechar=quotechar)
        for row in csv_vals:
            values = {}
            for key, value in row.items():
                if key in mappings:
                    if value in mappings[key]:
                        values[key] = mappings[key][value]
                    else:
                        values[key] = value
                else:
                    values[key] = value
            overall_values.append(values)

        j2 = jinja2.Environment(loader=jinja2.BaseLoader,
                                trim_blocks=False).from_string(config['output']['template'])
        try:
            rendered = j2.render({'values': overall_values})
        except Exception as exc:
            logger.error("got exception: %s" % exc)
            sys.exit()
        output += rendered
    with open(args.output, 'w') as f:
        f.write(output)
