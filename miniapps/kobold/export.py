import os
import json
import csv
import sys
import pandas as pd
import re
from loguru import logger
from dotenv import load_dotenv
from benedict import benedict

# veritas
from veritas.devicemanagement import scrapli as dm
from veritas.tools import tools


def get_value(values, keys):
    if isinstance(values, list):
        my_list = []
        for value in values:
            my_list.append(get_value(value.get(keys[0]), keys[1:]))
        return my_list
    elif isinstance(values, str):
        return values
    if len(keys) == 1:
        if values is None:
            return ''
        else:
            return values.get(keys[0])
    return get_value(values.get(keys[0]), keys[1:])

def get_number_of_rows(raw_data):
    rows = -1
    for key, values in raw_data.items():
        if isinstance(values, list):
            if rows == -1:
                rows = len(values)
            else:
                # we have multiple lists and the number of rows
                # differ. In this case we are not able to export the data
                if rows != len(values):
                    logger.error('the number of rows differ for the results')
                    return None
    return rows

def get_device_config_and_facts(kobold, sot, device_properties):
    device_facts = {}

    print(device_properties)

    device_ip = device_properties.get('primary_ip4',{}).get('address')
    # check if device_ip is cidr notation
    device_ip=device_ip.split('/')[0]
    platform = device_properties.get('platform',{}).get('name')
    # sometimes devices have no manufacturer
    manfctrr = device_properties.get('platform',{}).get('manufacturer',{})
    if not manfctrr or manfctrr == 'None':
        logger.info('this device has no manufacturer; using cisco')
        manufacturer = 'cisco'
    else:
        manufacturer = manfctrr.get('name','cisco')

    # Get the path to the directory this file is in
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    # Connect the path with the '.env' file name
    load_dotenv(os.path.join(BASEDIR, '.env'))
    
    # get username and password
    username, password = kobold.get_username_and_password()

    logger.info(f'ssh to {username}@{device_ip}:{kobold.get_tcp_port()} on platform {platform}')
    conn = dm.Devicemanagement(ip=device_ip,
                               platform=platform,
                               manufacturer=manufacturer.lower(),
                               username=username,
                               password=password,
                               port=kobold.get_tcp_port(),
                               scrapli_loglevel=kobold.get_scrapli_loglevel())

    # retrieve facts like fqdn, model and serialnumber
    logger.debug(f'now gathering facts from {device_ip}')
    device_facts = conn.get_facts()
    if device_facts is None:
        logger.error('got no facts; skipping device')
        if conn:
            conn.close()
        return None, None
    device_facts['args.device'] = device_ip

    # retrieve device config
    logger.info("getting running-config")
    try:
        device_config = conn.get_config("running-config")
    except Exception as exc:
        logger.error("could not receive device config from %s; got exception %s" % (device_ip, exc))
        return None, None
    if device_config is None:
        logger.error(f'could not retrieve device config from {device_ip}')
        conn.close()
        return None, None
    conn.close()

    return device_config, device_facts

def get_device_data_to_export(kobold, sot, task, devices):

    """
    prepare data to export by scanning through ALL devices and build table
    """

    # our list of dicts that contains the data we export
    data_to_export = []
    # some defaults
    calculate_checksum = False
    header_written = False

    # columns is the list of device/interface properties the user wants to export
    columns = task.get('columns').replace(' ','').split(',')

    for device in devices:
        device_property = {}
        for column in columns:
            data = get_value(device, column.split('.'))
            logger.debug(f'column={column} data={data}')
            device_property[column] = data
        
        number_of_rows = get_number_of_rows(device_property)
        if not number_of_rows:
            logger.error('number of rows are different for some columns')
            continue
        logger.debug(f'number_of_rows={number_of_rows}')

        # first add header if user wants it
        if 'header' in task and not header_written:
            header_written = True
            row = []
            for column in columns:
                row.append(column)
            data_to_export.append(row)

        # loop through the number of rows
        for n in range(number_of_rows):
            # initialize empty row
            row = [None] * len(columns)
            # and set column to 0
            number_of_column = 0
            for column in columns:
                # check if we have to calculate an MD5 sum
                if 'checksum' in column:
                    calculate_checksum = True
                if isinstance(device_property[column], str):
                    row[number_of_column] = device_property[column]
                else:
                    if device_property[column] is None:
                        row[number_of_column] = 'null'
                    else:
                        dta =  device_property[column][n]
                        if isinstance(dta, list):
                            if len(dta) > 0:
                                row[number_of_column] = dta[0]
                            else:
                                row[number_of_column] = ""
                        else:
                            row[number_of_column] = dta
                number_of_column += 1
            # calculate checksum if necessary
            if calculate_checksum:
                row[len(columns)-1] = tools.calculate_md5(row)

            # now put row to the list of exported values
            data_to_export.append(row)
    return data_to_export

def export_as_csv(task, data_to_export):
    logger.info(f'exporting {len(data_to_export)} entries as CSV')
    delimiter = task.get('delimiter',',')
    quotechar = task.get('quotechar','|')
    quoting_cf = task.get('quoting', 'minimal')
    filename = task.get('filename','export.csv')

    if quoting_cf == "none":
        quoting = csv.QUOTE_NONE
    elif quoting_cf == "all":
        quoting = csv.QUOTE_ALL
    elif quoting_cf == "nonnumeric":
        quoting = csv.QUOTE_NONNUMERIC
    else:
        quoting = csv.QUOTE_MINIMAL

    # create directory if it does not exsists
    directory = os.path.dirname(filename)
    if not os.path.exists(directory):
        os.makedirs(directory)

    logger.info(f'exporting data to {filename}')

    # now write our csv file
    with open(filename, 'w', newline='') as csvfile:
        export_writer = csv.writer(csvfile, delimiter=delimiter, quotechar=quotechar, quoting=quoting)
        for line in data_to_export:
            export_writer.writerow(line)

def export_as_excel(task, data_to_export):

    filename = task.get('filename','export.xlsx')
    logger.bind(extra='exp properties').info(f'exporting data as EXCEL to {filename}')

    # create directory if it does not exsists
    directory = os.path.dirname(filename)
    if not os.path.exists(directory):
        os.makedirs(directory)

    if task.get('header'):
        headers = data_to_export[0]
        print(headers)

    df = pd.DataFrame(data_to_export)
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Export', startrow=0, header=False, index=False)
    writer.close()

def export_device_properties(kobold, sot, task, devices):
    data_to_export = get_device_data_to_export(kobold, sot, task, devices)
    if len(data_to_export) == 0:
        logger.bind(extra='export').info('got no data to export')
        return
    if task.get('format') == 'csv':
        return export_as_csv(task, data_to_export)
    if task.get('format') == 'excel' or task.get('format') == 'xlsx':
        return export_as_excel(task, data_to_export)

def export_config_and_facts(kobold, sot, task, device_properties):

    hostname = device_properties.get('hostname')
    logger.debug(f'getting config and facts from {hostname}')
    device_config, device_facts = get_device_config_and_facts(kobold, sot, device_properties)
    content = task.get('content')
    BASEDIR = os.path.abspath(os.path.dirname(__file__))

    if 'config' in content:
        filename = "%s/%s/%s.conf" % (
            BASEDIR, 
            task.get('directory','./configs'), 
            hostname)
        subdir = os.path.dirname(filename)
        if not os.path.exists(subdir):
                logger.info(f'creating missing directory {subdir}')
                os.makedirs(subdir)

        logger.info(f'writing config to {filename}')
        try:
            with open(filename, 'w') as f:
                f.write(device_config)
        except Exception as exc:
            logger.error(f'could not write config; got exception {exc}')

    if 'facts' in content:
        hostname = device_properties.get('hostname')
        filename = "%s/%s/%s.facts" % (
            BASEDIR, 
            task.get('directory','./configs'), 
            hostname)
        subdir = os.path.dirname(filename)
        if not os.path.exists(subdir):
                logger.info(f'creating missing directory {subdir}')
                os.makedirs(subdir)

        logger.info(f'writing facts to {filename}')
        try:
            with open(filename, 'w') as f:
                f.write(json.dumps(device_facts,indent=4))
        except Exception as exc:
            logger.error(f'could not write facts; got exception {exc}')

def get_val(p, data):
    key = p.replace('__','')

    if key.startswith('cf_'):
        key = ['custom_field_data', key.replace('cf_','')]
        return tools.get_value_from_dict(data, key)
    else:
        # eg site_slug
        if '_' in key:
            return tools.get_value_from_dict(data, key.split('_'))
        else:
            if isinstance(key, str):
                return tools.get_value_from_dict(data, [key])
            else:
                return tools.get_value_from_dict(data, key)

def pattern_to_filename(pattern, data):
    logger.debug(f'getting filename from {pattern}')
    
    final_path = []
    separator = re.compile(".*?__(.*?)__.*?")
    hldm = benedict(data, keyattr_dynamic=True)

    path = pattern.split('/')
    logger.debug(f'list of path={path}')

    for item in path:
        if '__' not in item:
            final_path.append(item)
            continue

        match = separator.match(item)
        if match:
            key = match.group(1)
            if key.startswith('cf_'):
                custom_fields = hldm['custom_field_data']
                try:
                    value = custom_fields[key.replace('cf_','')].replace(' ','_').replace('/','_')
                    final_item = item.replace(f'__{key}__', value)
                    logger.debug(f'key={key} value={final_item}')
                    final_path.append(final_item)
                except Exception:
                    logger.error(f'unknown key {key}')
            else:
                try:
                    value = hldm[key]
                    final_item = item.replace(f'__{key}__', value)
                    logger.debug(f'key={key} value={final_item}')
                    final_path.append(final_item)
                except Exception:
                    logger.error(f'unknown key {key}')

    final_pattern = '/'.join(final_path)
    logger.debug(f'final pattern={final_pattern}')
    return final_pattern

def export_hldm(kobold, sot, task, devices):
    filename_pattern = task.get('filename', '__name__')
    subdir_pattern = task.get('directory', '')

    for device in devices:
        hostname = device.get('name')
        logger.debug(f'exporting HLDM of {hostname}')
        hldm = sot.get.hldm(device=hostname)[0]
        subdir = pattern_to_filename(subdir_pattern, hldm)
        filename = pattern_to_filename(filename_pattern, hldm)

        logger.debug(f'writing HLDM to subdir {subdir} filename {filename}')
        if not os.path.exists(subdir):
                logger.info(f'creating missing directory {subdir}')
                os.makedirs(subdir)
        with open(f'{subdir}/{filename}', "w") as f:
            f.write(json.dumps(hldm, indent=4))

def export(kobold, sot, tasks, devices):
    logger.info(f'exporting {tasks}')

    for task in tasks:
        content = task.get('content')
        if 'config' in content or 'facts' in content:
            for device in  devices:
                export_config_and_facts(kobold, sot, task, device)
        elif 'hldm' in content:
            export_hldm(kobold, sot, task, devices)
        elif 'properties' in content:
            # export columns of all devices
            export_device_properties(kobold, sot, task, devices)
