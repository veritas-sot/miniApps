#!/usr/bin/env python

import argparse
import logging
import yaml
import os
import json
from veritas.sot import sot


BASEDIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_CONFIG_FILE = "./conf/convert_csv.yaml"

if __name__ == "__main__":

    device_ip_in_sot = {}
    device_names_in_sot = {}
    device_names_short_in_sot = {}
    number_of_missing_devices = 0
    number_of_found_devices = 0

    parser = argparse.ArgumentParser()

    # the user can enter a different config file
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--diff', type=str, required=False)

    args = parser.parse_args()
    sot = sot.Sot(token="", 
              url="")

    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)s - %(message)s")

    # get all devices form SOT
    raw = sot.get \
            .as_dict \
            .query(name='device_properties', query_params={})
    for device in raw['data']['devices']:
            hostname = device.get('hostname')
            primary_ip = device.get('primary_ip4')
            device_names_in_sot[hostname.lower()] = primary_ip
            device_names_short_in_sot[hostname.split('.')[0].lower()] = primary_ip

    # print(json.dumps(device_names_in_sot, indent=4))
    # print(json.dumps(device_names_short_in_sot, indent=4))

    with open(args.input) as f:
        inventory = yaml.safe_load(f.read())

    if args.diff:
        diff_file = open(args.diff,"w")

    for device in inventory:
        hostname = device.get("hostname").lower().split(' ')[0]
        host_shorted = hostname.split('.')[0].lower()
        if hostname not in device_names_in_sot and host_shorted not in device_names_short_in_sot:
            # check if hostname without domain is in SOT
            number_of_missing_devices += 1
            # print(f'device {hostname} NOT found in SOT')
            if args.diff:
                # missing = f'- hostname: {device.get("hostname")}\n  host: {device.get("host")}\n  platform: {device.get("platform")}\n  city: {device.get("city")}\n  country: {device.get("country")}\n'
                missing = f'- hostname: {device.get("hostname")}\n  host: {device.get("host")}\n  platform: {device.get("platform")}\n'
                diff_file.write(missing)        
        else:
            number_of_found_devices += 1

    if args.diff:
        diff_file.close()
    
    print(f'Found: {number_of_found_devices} missing: {number_of_missing_devices}')