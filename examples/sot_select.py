#!/usr/bin/env python

import logging
import json
from veritas.sot import sot as sot

logging.basicConfig(level=logging.DEBUG)

my_sot = sot.Sot(token="your_token", 
                 url="http://ip_or_name:port")

# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .normalize(False) \
#                 .where('location=default-site or location=site_1')
# print(devices)

# devices = my_sot.select(['hostname']) \
#                 .using('nb.devices') \
#                 .normalize(False) \
#                 .where('location=default-site')
# print(devices)

# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .normalize(False) \
#                 .where('role=default-role')
# print(devices)

# devices = my_sot.select('hostname') \
#                 .using('nb.devices') \
#                 .normalize(False) \
#                 .where('platform=ios or platform=offline')
# print(devices)

# devices = my_sot.select('hostname', 'primary_ip4', 'platform','interfaces') \
#                 .using('nb.devices') \
#                 .normalize(True) \
#                 .where()
# print(devices)

# prefixes = my_sot.select(['prefix','description','vlan', 'site']) \
#                 .using('nb.ipam.prefix') \
#                 .normalize(False) \
#                 .where('within_include=192.168.0.0/24')
# print(prefixes)

# all_prefixe = my_sot.select(['prefix','description','vlan', 'site']) \
#                 .using('nb.ipam.prefix') \
#                 .normalize(False) \
#                 .where()
# print(all_prefixe)

# devices = my_sot.select('id, hostname') \
#                 .using('nb.devices') \
#                 .normalize(True) \
#                 .where('primary_ip4=192.168.0.1')
# print(devices)

# all_vlans = my_sot.select('vid, location') \
#                 .using('nb.ipam.vlan') \
#                 .normalize(False) \
#                 .where()
# print(all_vlans)

# loc_vlans = my_sot.select('vid, location') \
#                 .using('nb.ipam.vlan') \
#                 .normalize(False) \
#                 .where('location=site_1')
# print(loc_vlans)

# all_sites = my_sot.select('locations') \
#                 .using('nb.general') \
#                 .normalize(False) \
#                 .where()
# print(all_sites)

# all_tags = my_sot.select('tags') \
#                 .using('nb.general') \
#                 .normalize(False) \
#                 .where()
# print(all_tags)

# tag = my_sot.select('tags') \
#                 .using('nb.general') \
#                 .normalize(False) \
#                 .where('name=test')
# print(tag)

