import logging
import yaml
import json
import ipaddress
import os
import export
import glob
from veritas.devicemanagement import devicemanagement as dm


def get_config_and_facts(args, device_properties, kobold_config):
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    hostname = device_properties.get('hostname')
    device_ip = device_properties.get('primary_ip4',{}).get('address')
    device_config = None
    device_facts = None
    
    if args.use_import:
        filename_conf = "%s/%s/%s.conf" %(BASEDIR, kobold_config.get('configs','./configs'), hostname)
        filename_facts = "%s/%s/%s.facts" %(BASEDIR, kobold_config.get('configs','./configs'), hostname)
        try:
            with open(filename_conf, "r") as f:
                device_config = f.read()
                logging.debug(f'successfully imported config {filename_conf}')
            with open(filename_facts, "r") as f:
                device_facts = json.load(f)
                logging.debug(f'successfully imported facts {filename_facts}')
        except Exception as exc:
            logging.error(f'could not read (or parse) {filename_conf}')

    if device_config is None or device_facts is None:
        # todo checken ob das mit dem usernamen ueberhaupt geht; wo kommt der her?
        conn = dm.Devicemanagement(ip=device_ip,
                                   platform=device_defaults.get('platform','ios'),
                                   manufacturer=device_defaults.get('manufacturer','cisco'),
                                   username=username,
                                   password=password,
                                   port=args.port,
                                   scrapli_loglevel=args.scrapli_loglevel)

        try:
            device_facts = conn.get_facts()
            device_config = conn.get_config("running-config")
        except Exception as exc:
            logging.error("could not receive device config or facts from %s; got exception %s" % (device, exc))
            return device_config, device_facts
    return device_config, device_facts

def filter_device_list(args, sot, devices, job, kobold_config):
    logging.debug('filtering device_list')
    filtered_device_list = []
    filtered_device_configs = {}
    filtered_device_facts = {}

    for device_id, device_properties in devices.items():
        device_config, device_facts = get_config_and_facts(args, device_properties, kobold_config)
        platform = device_properties.get('platform')
        # the platform might be "None" (str) if the device is not "properly" configured
        if platform == "None" or platform is None:
            platform = 'ios'
        else:
            platform = platform.get('slug')

        if device_config is None:
            logging.error('could not retrieve device config')
            continue
        # parse config
        configparser = sot.configparser(config=device_config, platform=platform)
        # get overall policy. The default is or
        # or: True if global_config __OR__ interfaces_config matches
        # and: True if global_config __AND__ interfaces_config matches
        overall_policy = job.get('policy','or')
        matched_on_global_config = False
        matched_on_interfaces = False
        matched_interfaces = []
        first_run = True
        if 'global_config' in job:
            global_policy = job['global_config'].get('policy','or')
            logging.debug(f'filtering global config; policy: {global_policy}')
            # parse each entry
            matches = []
            for item in job['global_config'].get('patterns',[]):
                # we create a list of True and False
                matches.append(configparser.find_in_global(item))
            # now check the result depending on our global_policy
            if 'or' == global_policy:
                matched_on_global_config = True in matches
            else:
                matched_on_global_config = False not in matches
        if 'interface_config' in job:
            interface_policy = job['interface_config'].get('policy','or')
            logging.debug(f'filtering interface config; policy: {interface_policy}')
            # parse each entry
            matches = []
            for item in job['interface_config'].get('patterns',[]):
                interfaces = configparser.find_in_interfaces(item)
                if len(interfaces) > 0:
                    matches.append(True)
                    for interface in interfaces:
                        matched_interfaces.append(interface)

                if 'and' == interface_policy:
                    # when using AND as policy we have to check if some interfaces are part
                    # of ALL local results. 
                    if first_run:
                        # we use the result of the first result completely because we have no other 
                        # results to consider
                        first_run = False
                        matched_interfaces = interfaces
                    else:
                        # if it is not the first run we check if one ore more interfaces are part of the
                        # current matched_interfaces (the result so far) and the new interfaces
                        temp_interfaces = []
                        for interface in interfaces:
                            if interface in matched_interfaces:
                                # only interfaces that are part of both results are used
                                # this is the AND logic
                                temp_interfaces.append(interface)
                        matched_interfaces = temp_interfaces
                    logging.debug(f'matched_interfaces so far: {matched_interfaces}')

            # now check the result depending on our interface_policy
            if 'or' == interface_policy:
                matched_on_interfaces = True in matches
            else:
                matched_on_interfaces = False not in matches

        logging.debug(f'matched_on_global_config={matched_on_global_config} matched_on_interfaces={matched_on_interfaces}')

        # if no global_config or no interface_config is there: set to False and policy to or
        # in this case only the remaining option is used
        if 'global_config' not in job:
                matched_on_global_config = False
                policy = 'or'
        if 'interface_config' not in job:
                matched_on_interfaces = False
                policy = 'or'

        # remove duplicate interfaces / if policy is AND this should
        # never happen but if poliocy is or it can happen
        unique_interfaces = []
        for iface in matched_interfaces:
            if iface not in unique_interfaces:
                unique_interfaces.append(iface)

        if 'or' == overall_policy:
            if matched_on_global_config or matched_on_interfaces:
                logging.debug(f'policy: {overall_policy} adding device to list')
                device = devices.get(device_id)
                if matched_interfaces:
                    device.update({'interfaces': unique_interfaces})
                filtered_device_list.append(device)
                filtered_device_configs[device_id] = device_config
                filtered_device_facts[device_id] = device_facts
        else:
            # if no global_config or no interface_config is there: set to True
            if matched_on_global_config and matched_on_interfaces:
                logging.debug(f'policy: {overall_policy} adding device to list')
                device = devices.get(device_id)
                if matched_interfaces:
                    device.update({'interfaces': unique_interfaces})
                filtered_device_list.append(device)
                filtered_device_configs[device_id] = device_config
                filtered_device_facts[device_id] = device_facts

    return filtered_device_list, filtered_device_configs, filtered_device_facts

def parse_configs(sot, job, kobold_config):
    logging.debug('filtering device_list by parsing configs')
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    device_list = {}
    # device_configs = {}
    # device_facts = {}
    
    # get the list of patterns from our job config
    patterns = job.get('devices',{}).get('config',{})

    config_dir = "%s/%s" % (BASEDIR, kobold_config.get('configs','./configs'))
    logging.debug(f'reading all configs in config_dir')
    for filename in glob.glob(os.path.join(config_dir, "*.conf")):
        hostname = os.path.basename(filename).split('.conf')[0]
        with open(filename) as f:
            logging.debug(f'reading config {filename}')
            device_config = f.read()
            for pattern in patterns:
                for key, value in pattern.items():
                    for line in device_config.splitlines():
                        if value in line:
                            logging.debug(f'found pattern {pattern} in config of {hostname}')
                            query = kobold_config.get('queries', {}).get('devices')
                            query = query.replace('__name__', 'name')
                            data = sot.get.as_dict.query(query=query, query_params={'name': hostname}).get('data',{})
                            devices = data.get('devices', {})
                            if devices and len(devices) > 0:
                                for device in devices:
                                    id = device.get('id')
                                    device_list[id] = device
                                    # device_configs[id] = device_config
                                    # filename_facts = "%s/%s/%s.facts" %(BASEDIR, kobold_config.get('configs','./configs'), hostname)
                                    # try:
                                    #     with open(filename_facts, "r") as f:
                                    #         facts = json.load(f)
                                    #         device_facts[id] = facts
                                    #         logging.debug(f'successfully imported facts {filename_facts}')
                                    # except Exception as exc:
                                    #     logging.error(f'could not read (or parse) {filename_conf}')

    return device_list

def get_value(old_value, facts):
    value = old_value
    if isinstance(old_value, str) and 'device_facts__' in old_value:
        t = old_value.split('device_facts__')[1]
        if 'join__' in t:
            x = t.split('join__')[1]
            value = ','.join(facts.get(x))
        else:
            value = facts.get(t)
    return value

def tag_management(sot, task, device_list):
    scope = task.get('scope')
    configured_tags = task.get('tag', [])
    if isinstance(configured_tags, str):
        tags = [ configured_tags ]
    else:
        tags = configured_tags
    if scope is None or len(tags) == 0:
        logging.error(f'scope and tags must be configured to set tags')
        return
    for device in device_list:
        hostname = device.get('hostname')
        if scope == "dcim.interface":
            for interface in device.get('interfaces', []):
                if 'add_tag' in task:
                    logging.info(f'adding tag {tags} on {hostname}/{interface}')
                    sot.device(hostname).interface(interface).add_tags(tags)
                elif 'set_tag' in task:
                    logging.info(f'setting tag {tags} on {hostname}/{interface}')
                    sot.device(hostname).interface(interface).set_tags(tags)
                elif 'delete_tag':
                    logging.info(f'deleting tag {tags} on {hostname}/{interface}')
                    sot.device(hostname).interface(interface).delete_tags(tags)
        elif scope == "dcim.device":
            if 'add_tag' in task:
                logging.info(f'add tag {tags} on {hostname}')
                sot.device(hostname).add_tags(tags)
            elif 'set_tag' in task:
                logging.info(f'setting tag {tags} on {hostname}')
                sot.device(hostname).set_tags(tags)
            elif 'delete_tag' in task:
                logging.info(f'deleting tag {tags} on {hostname}')
                sot.device(hostname).delete_tags(tags)

def custom_field(sot, task, device_list):
    custom_fields = task.get('custom_field')
    for device in device_list:
        hostname = device.get('hostname')
        device_scope = {}
        interface_scope = {}
        for properties in custom_fields:
            scope = "device"
            if 'scope' in properties:
                scope = properties.get('scope')
                del properties['scope']
            if scope == "dcim.device":
                logging.info(f'setting custom field {properties} on {hostname}')
                device_scope.update(properties)
            elif scope == "dcim.interface":
                for interface in device.get('interfaces', []):
                    logging.info(f'setting custom field {properties} on {hostname}/{interface}')
                    if interface not in interface_scope:
                        interface_scope[interface] = {}
                    interface_scope[interface].update(properties)
        # all custom fields of a device are POSTed in one operation
        logging.debug(f'adding device scope custom fields to {hostname}')
        sot.device(hostname).set_customfield(properties)
        for interface in interface_scope:
            logging.debug(f'adding interface scope custom fields to {hostname}/{interface}')
            sot.device(hostname).interface(interface).set_customfield(interface_scope[interface])

def update_device(sot, task, device_list, device_facts):
    properties = {}
    new_values = task.get('update_device')
    for device in device_list:
        hostname = device.get('hostname')
        device_id = device.get('id')
        facts = device_facts.get(device_id)
        # facts = device_facts.get(dev)
        for value in new_values:
            for key, value in value.items():
                value = get_value(value, facts)
                if '__slug' in key:
                    k = key.split('__slug')[0]
                    properties[k] = {'slug': value}
                else:
                    properties[key] = value
        logging.info(f'updating device {hostname} properties {properties}')
        sot.device(hostname).update(properties, False)

def update_interface(sot, task, device_list, device_facts):
    properties = {}
    new_values = task.get('update_interface')
    for device in device_list:
        hostname = device.get('hostname')
        device_id = device.get('id')
        facts = device_facts.get(device_id)
        for value in new_values:
            for key, value in value.items():
                value = get_value(value, facts)
                if '__slug' in key:
                    k = key.split('__slug')[0]
                    properties[k] = {'slug': value}
                else:
                    properties[key] = value
        for interface in device.get('interfaces', []):
            logging.info(f'updating interface {hostname}/{interface} properties {properties}')
            sot.device(hostname).interface(interface).update(properties)

def run_playbook(args, sot, kobold_config):
    logging.info(f'running playbook {args.playbook}')
    device_list = []

    # load playbook
    with open(args.playbook) as f:
        try:
            playbook = yaml.safe_load(f.read())
        except Exception as exc:
            logging.error("could not parse yaml file %s; exception: %s" % (args.playbook, exc))
            return None
    run_job = None
    if args.job:
        run_job = args.job.split(',')

    for job in playbook.get('jobs'):
        pb_id = job.get('job')
        if run_job and str(pb_id) not in run_job:
            logging.debug(f'skipping job {pb_id}')
            continue
        pb_name = job.get('name')
        pb_comment = job.get('comment')

        # check how we get our list of devices
        logging.info(f'running job: {pb_id} name: {pb_name} / {pb_comment}')
        devices = job.get('devices')
        if 'config' in devices:
            device_list = parse_configs(sot, job, kobold_config)
        else:
            select = devices.get('select')
            get_from = devices.get('from')
            where = devices.get('where')
            device_list = sot.select(select) \
                             .using(get_from) \
                             .normalize(False) \
                             .where(where)
        if 'global_config' in job or 'interface_config' in job:
            device_list, device_configs, device_facts = filter_device_list(args, sot, device_list, job, kobold_config)

        logging.debug(f'after filtering the device list {len(device_list)} are remaining')
        if len(device_list) == 0:
            logging.info(f'no host matches specification')
            return

        tasks = job.get('tasks')
        if tasks is None:
            logging.error(f'no task configured!!!')
            continue
        for task in tasks:
            if 'export' in task:
                export.export(args, sot, task['export'], device_list, kobold_config)
            if 'add_tag' in task or 'set_tag' in task or 'delete_tag' in task:
                tag_management(sot, task, device_list)
            if 'custom_field' in task:
                custom_field(sot, task, device_list)
            if 'update_device' in task:
                update_device(sot, task, device_list, device_facts)
            if 'update_interface' in task:
                update_interface(sot, task, device_list, device_facts)