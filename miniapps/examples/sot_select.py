#!/usr/bin/env python

import logging
import json
from veritas.sot import sot as sot


my_sot = sot.Sot(token="your_token", 
                 url="http://ip_or_name:port")

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
#                 .where('name=["lab.local","switch.local"]')
# print(devices)

# get all hosts of a location
# devices = my_sot.select(['hostname']) \
#                 .using('nb.devices') \
#                 .where('location=default-site')
# print(devices)

# get all hosts of two locations
# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .where('location=default-site or location=site_1')
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
#                 .where('within_include=192.168.0.0/16')
# print(prefixes)

# get ALL prefixes with description, vlan and location
# all_prefixe = my_sot.select(['prefix','description','vlan', 'location']) \
#                 .using('nb.prefixes') \
#                 .where()
# print(all_prefixe)

# get id, hostname, and primary_ip of the host with IP=192.168.0.1
# devices = my_sot.select('id, hostname, primary_ip4') \
#                 .using('nb.ipaddresses') \
#                 .where('address=192.168.0.1')
# print(json.dumps(devices, indent=4))

# get ALL hosts where the IP address is of type host
# devices = my_sot.select('id, hostname, primary_ip4') \
#                 .using('nb.ipaddresses') \
#                 .where('type__ic=host')
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
