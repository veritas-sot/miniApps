#!/usr/bin/env python

import json
import logging
import os
import glob
import yaml
from veritas.sot import sot

log_format = '%(asctime)s %(levelname)s:%(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format)

sot = sot.Sot(token="your_token", 
              url="http://_your_url:port")

# adding multiple interfaces and vlans and set one of these interfaces as primary
vlans = [
    {"name": "my SVI 100", "vid": "100", "status": {"name": "Active"}, "location": {"name": "site_1"}}, 
    {"name": "trunked VLAN", "vid": "1", "status": {"name": "Active"}, "location": {"name": "site_1"}},
    {"name": "test", "vid": "999", "status": {"name": "Active"} }, 
]
interfaces = [
    {"name": "Port-channel10", "type": "1000base-t", "enabled": True, "description": "myPortChannel", "status": {"name": "Active"}}, 
    { "name": "GigabitEthernet0/0", 
      "type": "1000base-t", 
      "enabled": True, 
      "description": "to lab.local", 
      "status": {"name": "Active"}, 
      "mode": "access",
      # location based VLAN
      #"untagged_vlan": {'vid': 100, 'location': {'name': 'site_1'}}},
      # global VLAN
      "untagged_vlan": {'vid': 999}
    }, 
    {"name": "GigabitEthernet0/1", 
      "type": "1000base-t", 
      "enabled": True, 
      "description": "test", 
      "status": {"name": "Active"}, 
      "mode": "tagged", 
      "tagged_vlans": [ {'vid': 100, 'location': {'name': 'site_1'}} ]
    }, 
    {"name": "GigabitEthernet0/2", 
      "type": "1000base-t", 
      "enabled": True, 
      "description": "test", 
      "status": {"name": "Active"}, 
      "mode": "tagged-all", 
      "untagged_vlan": {'vid': 999}
    }, 
    ]

new_device = sot.onboarding \
    .interfaces(interfaces) \
    .primary_interface('GigabitEthernet0/1') \
    .vlans(vlans) \
    .add_prefix(False) \
    .add_device(name='test.local', 
                role='default-role', 
                device_type='iosv', 
                location='site_1', 
                status='Active')
print(new_device)

