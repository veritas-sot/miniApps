#!/usr/bin/env python

import json
import sys
import veritas.logging
from veritas.sot import sot as sot


veritas.logging.create_logger_environment(
    config={}, 
    cfg_loglevel="TRACE",
    cfg_loghandler=sys.stdout,
    app='example',
    uuid=None)

my_sot = sot.Sot(token="__token__", 
                 url="http://127.0.0.1:8080",
                 ssl_verify=False,
                 debug=True)

# res = boolean_parser("x=1 and y=3")
# res.logicop
# print(res)

# get id and hostname of a host
# devices = my_sot.select('id, hostname') \
#                 .using('nb.devices') \
#                 .where('name=lab.local')
# print(devices)

# get all hosts that includes 'local'
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('name__ic=local')
# print(devices)

# get id and hostname of a list of hosts
# devices = my_sot.select('id, hostname') \
#                 .using('nb.devices') \
#                 .where('name=lab-02.local or name=lab-04.local')
# print(devices)

# devices = my_sot.select('id, hostname') \
#              .using('nb.devices') \
#              .where(name=['lab-02.local', 'lab-04.local'])
# print(devices)

# get all hosts of a location
# devices = my_sot.select(['hostname']) \
#                 .using('nb.devices') \
#                 .where('location=default-site')
# print(devices)

# get all hosts of two locations
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('location=office or location=office')
# print(devices)

# get all hosts with a specific role
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('role=default-role')
# print(devices)

# get all hosts of platform ios and offline
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('platform=ios or platform=offline')
# print(devices)

# get all hosts and primary_ip
# devices = my_sot.select('hostname', 'primary_ip4') \
#                 .using('nb.devices') \
#                 .where()
# print(json.dumps(devices, indent=4))

# get hosts with cf_net=testnet and platform=offline
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('cf_net=testnet and platform=offline')
# print(devices)

# get hosts using multiple (different) cf_fields (or)
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('cf_net=testnet or cf_select=zwei')
# print(devices)

# get hostname and custom_field_data 
# devices = my_sot.select('hostname, custom_field_data') \
#                 .using('nb.devices') \
#                 .where('name=lab.local')
# print(devices)

# get all prefixes within a specififc range
# prefixes = my_sot.select(['prefix','description','vlan', 'location']) \
#                 .using('nb.prefixes') \
#                 .where('within_include=172.16.0.0/16')
# print(prefixes)

# get all prefixes within a specififc range and with a specific role
# prefixes = my_sot.select(['prefix','description','vlan', 'location']) \
#                 .using('nb.prefixes') \
#                 .where('within_include="172.16.0.0/16" and role=prefix_role')
# print(prefixes)

# get ALL prefixes with description, vlan and location
# all_prefixe = my_sot.select(['prefix','description','vlan', 'location']) \
#                 .using('nb.prefixes') \
#                 .where()
# print(all_prefixe)

# get hostname, and primary_ip of the host with IP=192.168.0.1
# devices = my_sot.select('address, primary_ip4_for') \
#                 .using('nb.ipaddresses') \
#                 .where('address=192.168.0.1')
# print(json.dumps(devices, indent=4))

# get ALL hosts where the IP address is of type host
# devices = my_sot.select('id, hostname, primary_ip4') \
#                 .using('nb.ipaddresses') \
#                 .where('type__ic=host')
# print(json.dumps(devices, indent=4))

# get hostname, device_type, role and primary_ip of hosts within prefix 192.168.0.0/24
# devices = my_sot.select('hostname, address, device_type, role, primary_ip4_for') \
#                 .using('nb.ipaddresses') \
#                 .where('prefix=192.168.0.0/24')
# print(json.dumps(devices, indent=4))

# get ALL vlans
# all_vlans = my_sot.select('vid, name, location') \
#                 .using('nb.vlans') \
#                 .where()
# print(all_vlans)

# get ALL vlans of a specific location
# loc_vlans = my_sot.select('vid, location') \
#                 .using('nb.vlans') \
#                 .where('location=default-site')
# print(loc_vlans)

# get ALL locations of our SOT
# all_locations = my_sot.select('locations') \
#                 .using('nb.general') \
#                 .where()
# print(all_locations)

# get ALL tags of our SOT
# all_tags = my_sot.select('tags') \
#                 .using('nb.general') \
#                 .where()
# print(all_tags)

# get dhcp tag 
# tag = my_sot.select('tags') \
#                 .using('nb.general') \
#                 .where('name=dhcp')
# print(tag)

# get HLDM of device
# hldm = my_sot.get.hldm(device="lab.local")
# print(json.dumps(hldm, indent=4))
