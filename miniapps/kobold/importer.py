import json
from loguru import logger
from benedict import benedict
from openpyxl import load_workbook


def read_json(filename):
    logger.debug(f'reading JSON from {filename}')
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
        return benedict(data, keyattr_dynamic=True)
    except Exception as exc:
        logger.error(f'failed to load JSON; got exception {exc}')
        return {}

def read_xlsx(filename):
    table = []
    workbook = load_workbook(filename = filename)
    worksheet = workbook.active
    # loop through table and build list of dict
    rows = worksheet.max_row
    columns = worksheet.max_column + 1 
    for row in range(2, rows + 1):
        line = benedict(keyattr_dynamic=True)
        for col in range(1, columns):
            key = worksheet.cell(row=1, column=col).value
            value = worksheet.cell(row=row, column=col).value
            line[key] = value
        table.append(line)
    return table

def import_hldm(sot, device_properties, dry_run=False):

    list_of_interfaces = []

    saved_values = benedict(keyattr_dynamic=True)
    for item in ['interfaces','config_context','primary_ip4','tags', 'hostname', 'custom_field_data']:
        if item in dict(device_properties):
            saved_values[item] = device_properties[item]
            del device_properties[item]

    # remove empty and null values
    device_properties.clean()

    # custom fields
    device_properties['custom_fields'] = saved_values.get('custom_field_data',{})

    # prepare interfaces
    if 'interfaces' in saved_values:
        for interface in saved_values['interfaces']:
            iface = benedict(interface, keyattr_dynamic=True)
            iface.clean()
            if 'type' in iface:
                iface['type'] = iface['type'].replace('A_','').replace('_','-').lower()
            list_of_interfaces.append(iface)
    else:
        list_of_interfaces.append({})

    # get primary ip
    primary_interface = saved_values['primary_ip4.interfaces[0].name']

    # new_device = sot.get.device('lab-01.local')
    if dry_run:
        name = device_properties.get('name')
        print(f'importing device {name} properties={device_properties} ' \
              f'interfaces={list_of_interfaces} primary={primary_interface}')
    else:
        name = device_properties.get('name')
        new_device = sot.onboarding \
                        .interfaces(list_of_interfaces) \
                        .primary_interface(primary_interface) \
                        .add_prefix(False) \
                        .add_device(device_properties)
        if new_device:
            logger.info(f'imported {name} to nautobot')
        else:
            logger.error(f'failed to import {name} to nautobot')

    # set tags
    list_of_tags = []
    tags = saved_values.get('tags')
    if tags:
        if isinstance(tags, str):
            # excel sheet
            list_of_tags = tags.split(',')
        elif isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    list_of_tags.append(tag)
                elif isinstance(tag, dict):
                    # hldm
                    if 'name' in tag:
                        list_of_tags.append(tag['name'])
        if dry_run:
            print(f'adding tags {list_of_tags}')
        else:
            sot.device(new_device.display).set_tags(list_of_tags)

def import_ipaddresses(sot, ipaddresses, dry_run=False):
    if dry_run:
        for ip in ipaddresses:
            print(f'importing {ip}')
        return
    success = sot.ipam.add_ip(ipaddresses)
    if success:
        logger.info('successfully imported IP-addresses')
    else:
        logger.error('failed to import IP-addresses')

def import_data(sot, args):
    if 'json' in args.filename:
        data = read_json(args.filename)
        # check which data we have
        if all(k in data for k in ('name','status','device_type', 'role')):
            import_hldm(sot, data)
    elif 'xlsx' in args.filename:
        data = read_xlsx(args.filename)
        if all(k in data[0] for k in ('address','namespace', 'status')):
            import_ipaddresses(sot, data, args.dry_run)
        elif all(k in data[0] for k in ('name','status','device_type', 'role')):
            for device in data:
                import_hldm(sot, device, args.dry_run)
    