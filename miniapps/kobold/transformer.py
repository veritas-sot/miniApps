import yaml
import re
import jinja2
from benedict import benedict
from loguru import logger

#### simple

def camel(s):
  s = re.sub(r"(_|-)+", " ", s).title().replace(" ", "")
  return ''.join([s[0].lower(), s[1:]])

def get_value_from_template(device, template):
    # read template
    with open(template) as f:
        template = f.read()
    j2 = jinja2.Environment(loader=jinja2.BaseLoader, trim_blocks=False).from_string(template)
    try:
        return j2.render({'values': device})
    except Exception as exc:
        logger.error("could not render template; got exception: %s" % exc)

    return ""

def run_simple_update(sot, config, template, 
                      where='name=', using='nb.devices', dry_run=False):
    """read config from file and update items depending on this config"""

    # the left part is the item the right part a modifier like upper or lower
    modifier = re.compile("__(.*?)@(.*?)__")
    zfill = re.compile("__(.*?)@zfill\((\d+)\)__")
    match_any_host = '^(?P<name>(.*))'

    # init vars
    named_groups = {}
    destinations = {}

    # compile named groups
    try:
        if config.get('source') == 'any':
            cfg = {'name': match_any_host}
        else:
            cfg = config.get('source', {}).get('named_groups','')
    except Exception as exc:
        logger.error(f'config error; got exception {exc}')
        return

    for item in cfg:
        logger.debug(f'named: {item} pattern: {cfg[item]}')
        named_groups[item] = re.compile(cfg[item])

    cfg = config.get('destination', {})
    for item in cfg:
        logger.debug(f'destination: {item} new value: {cfg[item]}')
        destinations[item] = cfg[item]

    # get items to update
    select = set()
    select.add('id')
    if using == 'nb.devices':
        for ng in named_groups:
            select.add(ng.split('.')[0])
    elif using == "nb.ipaddresses":
        select.add('address')
        select.add('interface_assignments')

    for key in named_groups.keys():
        select.add(key)
    logger.debug(f'select={select} using={using} where={where}')
    itemlist = sot.select(list(select)) \
                  .using(using) \
                  .where(where)

    if len(itemlist) == 0 and dry_run:
        print('nothing to do')
        return

    logger.info(f'got {len(itemlist)} item from our sot')

    # loop through items and check if it must be updated
    for row in itemlist:
        # we use benedict
        # the advantage is that we can easily get values from it
        # entity is the row we got from our SOT
        # this can be a device or an ip address
        entity = benedict(row, keyattr_dynamic=True)
        updates = benedict(keyattr_dynamic=True)

        if using == 'nb.devices':
            extra = entity['hostname']
            hostname_id = entity['id']
        elif using == "nb.ipaddresses":
            extra = entity['address']
            address_id = entity['id']
        else:
            logger.error(f'unknown or unsupported type {using}')
            return None

        # loop through named groups and check if pattern matches
        # matched_values contains all items that were found in entity
        # and for which the pattern matched
        matched_values = {}
        for ng_key, pattern in named_groups.items():
            # we have to check if the key can be found in our entity
            try:
                item = entity[ng_key]
            except KeyError:
                logger.error(f'key {ng_key} not found in entity')
                continue
            logger.bind(extra=extra).debug(f'key: {ng_key} pattern: {pattern} item: {item}')
            match = pattern.match(item)
            if match:
                for group, group_val in match.groupdict().items():
                    matched_values[group] = group_val

        if len(matched_values) == 0:
            logger.bind(extra=extra).debug('entity without matching group')

        # now matched_values is complete
        # we loop through the destinations and set the new value
        for parameter, orig_value in destinations.items():
            new_value = orig_value
            logger.bind(extra=extra).debug(f'parameter={parameter} new_value from config: {new_value}')
            for group, group_val in matched_values.items():

                if not isinstance(new_value, str):
                    logger.debug(f'new value {new_value} is of type {type(new_value)}')
                    updates[parameter] = new_value
                    continue

                # check if we have to fill up a named group
                # this is a special case because we have an argument
                match = zfill.match(new_value)
                if match:
                    item = match.group(1)
                    fill = match.group(2)
                    new_value = new_value.replace(f'__{group}@zfill({fill})__', group_val.zfill(int(fill)))

                match = modifier.match(new_value)
                # at first check if we have to use a emplate
                if template:
                    logger.debug('using template to get new_value')
                    new_value = get_value_from_template(row, template)
                # now check if we have some modifiers (upper, lower)
                elif match:
                    item = match.group(1)
                    mod = match.group(2)
                    logger.bind(extra=extra).debug(f'item={item} modifier={mod}')
                    if 'upper' == mod:
                        new_value = new_value.replace(f'__{group}@upper__', group_val.upper())
                    elif 'lower' == mod:
                        new_value = new_value.replace(f'__{group}@lower__', group_val.lower())
                    elif 'title' == mod:
                        new_value = new_value.replace(f'__{group}@title__', group_val.title())
                    elif 'capwords' == mod:
                        new_value = new_value.replace(f'__{group}@capwords__', group_val.capwords())
                    elif 'camel':
                        new_value = new_value.replace(f'__{group}@cammel__', camel(group_val))
                    else:
                        logger.error(f'unknown mod value {mod}')
                # otherwise replace named groups in new_value
                else:
                    new_value = new_value.replace(f'__{group}__', group_val)

                logger.bind(extra=extra).debug(f'parameter: {parameter} group {group} '\
                    f'group_val: {group_val} final new_value: {new_value}')
                if parameter.startswith('cf_'):
                    parameter = parameter.replace('cf_','')
                    if 'custom_fields' in updates:
                        updates['custom_fields'].update({parameter: new_value})
                    else:
                        updates['custom_fields'] = {parameter: new_value}
                else:
                    # because we use benedict we can easily set the new value
                    # the syntax of the key is like key.subkey.subsubkey
                    # eg location.location_type.name
                    updates[parameter] = new_value

        # now we are able to update the item in nautobot
        if len(updates) > 0:
            if using == 'nb.devices':
                if dry_run:
                    print(f'update {extra}; new values: {updates}')
                else:
                    try:
                        nb_obj = sot.get.device(name=hostname_id, by_id=True)
                        response = nb_obj.update(data=updates)
                        logger.bind(extra=extra).info(f'item updated; data={updates}; response={response}')
                    except Exception as exc:
                        logger.bind(extra=extra).error(f'could not update item {exc}')
            elif using == 'nb.ipaddresses':
                if dry_run:
                    print(f'update {extra}; new values: {updates}')
                else:
                    try:
                        nb_obj = sot.get.address(address=address_id, by_id=True)
                        response = nb_obj.update(data=updates)
                        logger.bind(extra=extra).info(f'item updated; data={updates}; response={response}')
                    except Exception as exc:
                        logger.bind(extra=extra).error(f'could not update item; got exception {exc}')

#### main

def transform(sot, args, kobold_config):
    jobs_yaml = read_yaml(args.filename)
    if not jobs_yaml:
        logger.error(f'failed to read YAML config {args.filename}')
        return False
    else:
        jobs = jobs_yaml.get('transform')

    for job in jobs:
        if args.job and jobs.get('job') != args.job:
            continue

        # get using, and where
        using =  job.get('source',{}).get('from')
        where =  args.where if args.where else job.get('source',{}).get('where')
        logger.debug(f'where={where} using={using}')

        # we do NOT want to transform all devices
        if not where:
            logger.error('there is no where clause specified. We do not want to update ALL devices')
            logger.error('Please use --devices name= if you realy want to update alles devices')
            print('there is no where clause specified. We do not want to update ALL devices')
            print('Please use --devices name= if you realy want to update alles devices')
            return
        
        run_simple_update(
            sot, job, args.template, where=where, using=using, dry_run=args.dry_run)

def read_yaml(filename):
    try:
        with open(filename) as f:
            return yaml.safe_load(f.read())
    except Exception as exc:
        logger.error(f'could not read or parse config; got exception {exc}')
        return None
