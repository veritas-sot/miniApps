import os
import json
import csv
import xlsxwriter
from loguru import logger
from veritas.devicemanagement import scrapli as dm
from veritas.tools import tools
from dotenv import load_dotenv


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
                    logger.error(f'the number of rows differ for the results')
                    return None
    return rows

def get_device_config_and_facts(kobold, sot, device_properties):
    device_facts = {}

    hostname = device_properties.get('hostname')
    device_ip = device_properties.get('primary_ip4',{}).get('address')
    # check if device_ip is cidr notation
    device_ip=device_ip.split('/')[0]
    platform = device_properties.get('platform',{}).get('name')
    manufacturer = device_properties.get('platform',{}).get('manufacturer',{}).get('name','cisco')

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
    calculate_checksum = False
    # get mapping to map column name to SOT property name
    mappings = kobold.get_mapping() # ('mappings',{}).get('export')
    # columns is the list of device/interface properties the user wants to export
    columns = task.get('columns').replace(' ','').split(',')

    header_written = False
    # loop through ALL devices
    for device_properties in devices:
        device_id = device_properties.get('id')
        hostname = device_properties.get('hostname')
        logger.debug(f'getting data of {hostname}')
        device_data = {}
        cf_fields = ""

        values = set()
        for column in columns:
            if column.startswith('cf_'):
                values.add('custom_field_data')
            elif '__' in column:
                values.add(column.split('__')[0])
            elif column == 'checksum':
                continue
            else:
                values.add(column)
        parameter = {'name': hostname}
        logger.debug(f'values {list(values)} parameter {parameter}')
        raw_data = sot.get.query(values=list(values),
                                 parameter=parameter)

        # we are getting a list with one device in it
        data = raw_data[0]
        # now get the values
        for column in columns:
            if 'checksum' in column:
                calculate_checksum = True
            #check if column name is in mapping
            if column in mappings:
                key = mappings.get(column).split('__')
            elif column.startswith('cf_'):
                key = ['custom_field_data', column.replace('cf_','')]
            else:
                key = column.split('__')
            device_data[column] = get_value(data, key)

        # now create the table for this device
        # the number of rows depends of the number of interfaces to export
        # if we do NOT have any interfaces the number of rows is 1
        # otherwise the number of rows is the number of interfaces
        number_of_rows = get_number_of_rows(device_data)
        if number_of_rows is None:
            # error: unequal numbers of rows detected
            continue
        if number_of_rows == -1:
            number_of_rows = 1
        logger.debug(f'the table has {number_of_rows} rows and {len(columns)} columns')
        # add header first of user wants it
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
                if isinstance(device_data[column], str):
                    row[number_of_column] = device_data[column]
                else:
                    if device_data[column] is None:
                        row[number_of_column] = 'null'
                    else:
                        row[number_of_column] = device_data[column][n]
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
    header = []
    table_start_col = 65 # 65=A
    table_start_row = 1
    number_of_cols = 0
    filename = task.get('filename','export.xlsx')
    
    logger.bind(extra='exp properties').info(f'exporting data as EXCEL to {filename}')

    # create directory if it does not exsists
    directory = os.path.dirname(filename)
    if not os.path.exists(directory):
        os.makedirs(directory)

    workbook = xlsxwriter.Workbook(filename)
    worksheet = workbook.add_worksheet()
    header_data = data_to_export.pop(0)
    number_of_cols = len(header_data)
    table_coordinations = '%s%s:%s%s' % (chr(table_start_col),
                                         table_start_row,
                                         chr(table_start_col + len(header_data) - 1),
                                         table_start_row + (len(data_to_export) ))
    for c in header_data:
        header.append({'header': c})
    worksheet.add_table(table_coordinations, {'data': data_to_export, 
                                              'header_row': True, 
                                              'columns': header
                                             })
    worksheet.autofit()
    workbook.close()

def export_device_properties(kobold, sot, task, devices):
    data_to_export = get_device_data_to_export(kobold, sot, task, devices)
    if len(data_to_export) == 0:
        logger.bind(extra='export').info(f'got no data to export')
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

def pattern_to_filename(path, data):
    prefix = ""
    indexes = []

    logger.debug(f'pattern_to_filename {path}')

    # check if pattern has any dynamic values
    if '__' not in path:
        return path

    # build a list of (static|dynamic) fields
    # we loop through our pattern and check if a '__' is found
    # if we found this pattern we add the corresponding start and end values to our list
    # it seems that there is no easy regex to get all __xxx__ matches if it is allowed
    # to use multiple occurences of this pattern like __cf_net____location/name__
    i = 0
    active = False
    while i < len(path) - 2:
        if '__' == path[i:i+2]:
            if active:
                indexes.append({'start': start, 'end': i+2})
                active = False
            else:
                start = i
                active = True
            i += 2
        else:
            i += 1
    if active:
        indexes.append({'start': start, 'end': len(path)})

    # now we have a list of all dynamic fields
    # we have to check if there is a gap between two fields
    # in this case there is a static value we use additionaly eg. 
    # __cf_net__xxx__location/name__ where xxx is a static value between the two dynamic fields

    last_index = 0
    for i in indexes:
        start = i.get('start')
        end = i.get('end')
        # logger.debug(f'start {start} end {end}')
        if last_index == 0 and start > last_index:
            value = path[last_index:start]
            prefix = "%s%s" % (prefix, value)
            # logger.debug(f'static value detected at {last_index} / {start} value {value}')
        elif start - last_index == 1:
            value = path[last_index:last_index+1]
            prefix = "%s%s" % (prefix, value)
            # logger.debug(f'static value detected at {last_index} value {value}')

        key = path[start:end]
        value = get_val(key, data)
        prefix = "%s%s" % (prefix, value)
        # logger.debug(f'dynamic value detected at {start} / {end} value {value}')

        last_index = end

    if last_index != len(path):
        value = path[last_index:]
        prefix = "%s%s" % (prefix, value)
        # logger.debug(f'static value at the end detected {last_index} value: {value}')

    return prefix

def export_hldm(kobold, sot, task, devices):
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    filename_pattern = task.get('filename', '__hostname__')
    subdir_pattern = task.get('directory', '')

    for device in devices:
        hostname = device.get('hostname')
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
    device_config = device_facts = None
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    conn = None

    for task in tasks:
        content = task.get('content')
        directory = task.get('directory')
        if content == 'properties':
            properties = task.get('columns')
            format = task.get('format','csv')

        if 'config' in content or 'facts' in content:
            for device in  devices:
                export_config_and_facts(kobold, sot, task, device)
        elif 'hldm' in content:
            export_hldm(kobold, sot, task, devices)
        elif 'properties' in content:
            # export columns of all devices
            export_device_properties(kobold, sot, task, devices)
