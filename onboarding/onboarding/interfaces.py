import logging
import json
from businesslogic import your_interfaces as user_int
from veritas.sot import sot as sot
from slugify import slugify
from ipaddress import IPv4Network


def get_list_of_interfaces(sot, args, device_fqdn, device_facts, device_defaults, ciscoconf):
    list_of_interfaces = []
    interfaces = ciscoconf.get_interfaces()

    # Port-channels are used as reference by some physical interfaces so
    # add logical interfaces to sot first
    for name in interfaces:
        if 'port-channel' in name.lower():
            logging.debug("port-channel interface: %s" % name)
            props = get_interface_properties(sot, 
                                             device_fqdn,
                                             device_facts,
                                             device_defaults, 
                                             ciscoconf, 
                                             name)
            # call business logic if the user wants some modifications
            user_int.interface_tags(sot, ciscoconf, interfaces)
            list_of_interfaces.append(props)

    # now add physical interface to sot
    for name in interfaces:
        if 'port-channel' not in name.lower():
            logging.debug("interface: %s" % name)
            props = get_interface_properties(sot, 
                                             device_fqdn,
                                             device_facts,
                                             device_defaults, 
                                             ciscoconf, 
                                             name)
            # call business logic if the user wants some mods
            user_int.interface_tags(sot, ciscoconf, props)
            list_of_interfaces.append(props)

    return list_of_interfaces

def get_interface_properties(sot, device_fqdn, device_facts, device_defaults, ciscoconf, name):
    # get interfaces
    interfaces = ciscoconf.get_interfaces()
    interface = interfaces.get(name)
    # set site
    site = device_defaults['site']

    # description must not be None
    description = interface.get('description')
    if description is None:
        description = ""

    device_id = device_facts['id'] if device_facts.get('id') else device_fqdn
    # set the basic properties of the device
    interface_properties = {
            'device': device_id,
            'name': name,
            'type': interface.get('type','1000base-t'),
            'enabled': 'shutdown' not in interface,
            'description': description,
            'status': {'name': 'Active'}
    }

    # check if interface is lag
    if 'channel_group' in interface:
        pc = "%s%s" % (ciscoconf.get_name("port-channel"), interface.get('channel_group'))
        logging.debug(f'interface {name} is part of port-channel {pc}')
        interface_properties.update({'lag': pc })

    # setting switchport or trunk
    if 'mode' in interface:
        mode = interface.get('mode')
        data = {}
        if mode == 'access':
            logging.debug("interface is access switchport: %s" % name)
            untagged_vlan = sot.get.id(item='vlan', vid=interface.get('vlan'), site=site)
            data = {"mode": "access",
                    "untagged_vlan": interface.get('vlan'),
                    "site": site}
        elif mode == 'trunk':
            logging.debug("interface is a tagged switchport: %s" % name)
            # this port is either a trunked with allowed vlans (mode: tagged)
            # or a trunk with all vlans mode: tagged-all
            if 'vlans_allowed' in interface:
                vlans = ",".join(interface.get('vlans_allowed'))
                data = {'mode': 'tagged', 'tagged_vlans': vlans}
            else:
                data = {"mode": "tagged-all", "site": site }

        if len(data) > 0:
            logging.debug("updating interface: %s" % name)
            interface_properties.update(data)

    return interface_properties

def update_interface(sot, args, device_fqdn, device_facts, interface_properties, current_sot_interfaces):
    name = interface_properties.get('name')

    if args.update:
        logging.info(f'update set; updating interface {name}')
        success = sot.device(device_fqdn) \
            .interface(name) \
            .update(interface_properties)
        if success:
            logging.debug(f'interface {name} updated')
        else:
            logging.debug(f'interface {name} not updated')
    else:
        logging.info(f'skipping interface {name}')

def assign_interfaces(sot, interface_name, device_fqdn, ciscoconf):
    # assign IP Address
    logging.debug(f'checking if there is a IP configured on {interface_name}')
    if ciscoconf.get_ipaddress(interface_name) is not None:
        addr = ciscoconf.get_ipaddress(interface_name)
        logging.debug("assigning %s on %s to %s" % (interface_name, device_fqdn, addr))
        success = sot.ipam \
            .assign(interface_name) \
            .on(device_fqdn) \
            .add_missing_ip(True) \
            .to(addr)
    else:
        logging.debug(f'no IP address configured on interface')

def vlans(sot, args, device_fqdn, ciscoconf, device_defaults):
    global_vlans, svi, trunk_vlans = ciscoconf.get_vlans()
    list_of_vlans = {}

    for vlan in global_vlans:
        vid = vlan.get('vid')
        name = vlan.get('name')
        list_of_vlans[vid] = {'name': name,
                              'status': {'name': 'Active'},
                              'site': {'name': slugify(device_defaults['site'])}}

    for vlan in svi:
        vid = vlan.get('vid')
        name = vlan.get('name')
        if vid not in list_of_vlans:
            list_of_vlans[vid] = {'name': name,
                                  'status': {'name': 'Active'},
                                  'site': {'name': slugify(device_defaults['site'])}}

    for vlan in trunk_vlans:
        vid = vlan.get('vid')
        name = vlan.get('name')
        if vid not in list_of_vlans:
            list_of_vlans[vid] = {'name': name,
                                  'status': {'name': 'Active'},
                                  'site': {'name': slugify(device_defaults['site'])}}

    if args.write_hldm or args.show_hldm:
        return list_of_vlans

    for vid, conf in list_of_vlans.items():
        try:
            vid_int = int(vid)
        except Exception:
            logging.error(f'could not convert string {vid} to int')
            continue
        sot.ipam.vlan(vid_int).add(conf)

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

# def convert_properties_to_id(sot, device_fqdn, device_facts, device_defaults, ciscoconf, interfaces, props):
#     site = device_defaults['site']
#     props['device'] = device_facts['id'] if device_facts.get('id') else {'name': device_fqdn}
#     if 'untagged_vlan' in props:
#         props_vlan_id = props.get('untagged_vlan')
#         vlan_id = sot.get.id(item='vlan', vid=props_vlan_id, site=site)
#         logging.debug(f'converted untagged_vlan {props_vlan_id} to {vlan_id}')
#         props['untagged_vlan'] = vlan_id
#     if 'tagged_vlans' in props:
#         tagged_vlans = []
#         props_vlan_id = props.get('tagged_vlans')
#         for vlan in props_vlan_id.split(','):
#             t = sot.get.id(item='vlan', vid=vlan, site=site)
#             tagged_vlans.append(t)
#         props['tagged_vlans'] = tagged_vlans
#     if 'lag' in props:
#         pc = props['lag']
#         props['lag'] = {'device': {'name': device_fqdn}, 'name': pc}
#     if 'site' in props:
#         site_name = props['site']
#         # site_id = sot_sites.get(site_name, site_name)
#         site_id = sot.get.id(item='site', name=site_name)
#         props['site'] = site_id
#     if 'tags' in props:
#         tags = props['tags']
#         tag_slugs = tags.get('tags')
#         content_types = tags.get('content_types')
#         tag_list = [sot.get.id(item='tag', slug=slug, content_types=content_types) for slug in tag_slugs.split(',')]
#         props['tags'] = tag_list

def get_primary_interface(primary_address, ciscoconf):
    primary_interface = {}
    interface_name = ciscoconf.get_interface_name_by_address(primary_address)

    # if primary_interface_name is none then the IP address was not configured on an interfcae
    # this can happen when using dhcp (strange but possible) or hsrp (more common)
    logging.debug(f'primary_interface_name set to {interface_name}')
    interface = ciscoconf.get_interface(interface_name)

    # if we have the right mask of the interface/ip we use this instead of a /32
    if interface is not None:
        primary_interface['name'] = interface_name
        # convert IP and MASK to cidr notation
        prefixlen = IPv4Network("0.0.0.0/%s" % interface.get('mask')).prefixlen
        primary_address = "%s/%s" % (interface.get('ip'), prefixlen)
        logging.debug(f'found primary interface; setting primary_address interface to {primary_address}')
        if interface.get('description') == None:
            logging.info("primary interface has no description configured; using 'primary interface'")
            primary_interface['description'] = "primary interface"

    return primary_interface