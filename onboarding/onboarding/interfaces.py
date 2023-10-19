import logging
import json
from businesslogic import your_interfaces as user_int
from veritas.sot import sot as sot
from slugify import slugify
from ipaddress import IPv4Network


def get_interface_properties(sot, device_fqdn, device_facts, device_defaults, ciscoconf):
    list_of_interfaces = []
    for name in ciscoconf.get_interfaces():
        #logging.debug("get property of interface: %s" % name)
        props = get_properties(sot,
                               device_fqdn,
                               device_facts,
                               device_defaults,
                               ciscoconf,
                               name)
        # call business logic if the user wants some modifications
        user_int.interface_tags(ciscoconf, props)
        list_of_interfaces.append(props)

    return list_of_interfaces

def get_properties(sot, device_fqdn, device_facts, device_defaults, ciscoconf, name):
    """returns all properties of the interface"""
    all_interfaces = ciscoconf.get_interfaces()
    interface = all_interfaces.get(name)

    # set location
    location = device_defaults['location']

    # description must not be None
    description = interface.get('description',"")
    # set the basic properties of the device
    interface_properties = {
            'name': name,
            'type': interface.get('type','1000base-t'),
            'enabled': 'shutdown' not in interface,
            'description': description,
            'status': {'name': 'Active'}
    }
    if 'ip' in interface:
        ipv4 = IPv4Network(f'{interface.get("ip")}/{interface.get("mask")}', strict=False)
        cidr = f'{interface.get("ip")}/{ipv4.prefixlen}'
        interface_properties.update({'ipv4': cidr})

    # check if interface is lag
    if 'channel_group' in interface:
        pc = "%s%s" % (ciscoconf.get_name("port-channel"), interface.get('channel_group'))
        # logging.debug(f'interface {name} is part of port-channel {pc}')
        interface_properties.update({'lag': {'name': pc }})

    # setting switchport or trunk
    if 'mode' in interface:
        mode = interface.get('mode')
        data = {}
        if mode == 'access':
            logging.debug("interface is access switchport: %s" % name)
            untagged_vlan = sot.get.id(item='vlan', vid=interface.get('vlan'), location=location)
            data = {"mode": "access",
                    "untagged_vlan": {'vid': interface.get('vlan'),
                                      'location': {'name': location}
                                     }
                   }
        elif mode == 'trunk':
            logging.debug("interface is a tagged switchport: %s" % name)
            # this port is either a trunk with allowed vlans (mode: tagged)
            # or a trunk with all vlans mode: tagged-all
            if 'vlans_allowed' in interface:
                vlans = []
                for vlan in interface.get('vlans_allowed'):
                    vlans.append({'vid': vlan,
                                  'location': {'name': location}
                                })
                data = {'mode': 'tagged', 
                        'tagged_vlans': vlans}
            else:
                data = {'mode': "tagged-all"}

        if len(data) > 0:
            logging.debug("updating interface: %s" % name)
            interface_properties.update(data)

    return interface_properties

def get_vlan_properties(device_fqdn, ciscoconf, device_defaults):
    global_vlans, svi, trunk_vlans = ciscoconf.get_vlans()
    list_of_vlans = []
    all_vlans = {}
    location = device_defaults['location']

    for vlan in global_vlans:
        vid = vlan.get('vid')
        name = vlan.get('name','')
        if '-' in vid or ',' in vid:
            continue
        if not f'{vid}__{location}' in all_vlans:
            all_vlans[f'{vid}__{location}'] = True
            list_of_vlans.append({'name': name,
                                  'vid': vid,
                                  'status': {'name': 'Active'},
                                  'location': {'name': location}})

    for vlan in svi:
        vid = vlan.get('vid')
        name = vlan.get('name','')
        if '-' in vid or ',' in vid:
            continue
        if not f'{vid}__{location}' in all_vlans:
            all_vlans[f'{vid}__{location}'] = True
            list_of_vlans.append({'name': name,
                                  'vid': vid,
                                  'status': {'name': 'Active'},
                                  'location': {'name': device_defaults['location']}})

    for vlan in trunk_vlans:
        vid = vlan.get('vid')
        name = vlan.get('name','')
        if '-' in vid or ',' in vid:
            continue
        if not f'{vid}__{location}' in all_vlans:
            all_vlans[f'{vid}__{location}'] = True
            list_of_vlans.append({'name': name,
                                  'vid': vid,
                                  'status': {'name': 'Active'},
                                  'location': {'name': device_defaults['location']}})

    return list_of_vlans

def get_interfaces_from_sot(sot, device_fqdn):
    current_sot_interfaces = {}
    interfaces = sot.select('interfaces') \
                    .using('nb.devices') \
                    .normalize(False) \
                    .where(f'name={device_fqdn}')
    if len(interfaces) == 0:
        return {}
    for iface in interfaces[0]['interfaces']:
        name = iface.get('name')
        current_sot_interfaces[name] = iface
    logging.debug(f'there are currently {len(current_sot_interfaces)} interfaces in the sot')

    return current_sot_interfaces

def get_primary_interface(primary_address, ciscoconf):
    primary_interface = {}
    interface_name = ciscoconf.get_interface_name_by_address(primary_address)
    interface = ciscoconf.get_interface(interface_name)

    # if we have the right mask of the interface/ip we use this instead of a /32
    if interface is not None:
        primary_interface['name'] = interface_name
        # convert IP and MASK to cidr notation
        prefixlen = IPv4Network("0.0.0.0/%s" % interface.get('mask')).prefixlen
        primary_interface['ip'] = "%s/%s" % (interface.get('ip'), prefixlen)
        logging.debug(f'found primary interface; setting primary_address interface to {primary_address}')
        if 'description' not in interface:
            logging.info("primary interface has no description configured; using 'primary interface'")
            primary_interface['description'] = "primary interface"
    else:
        logging.debug(f'found no interface, setting default values')
        primary_interface['name'] = "primaryInterface"
        primary_interface['description'] = "primary interface"
        primary_interface['ip'] = f'{primary_address}/32'

    return primary_interface