import argparse
import logging
import json
import yaml
import textfsm
import tabulate
import asyncio
import sys
import time
from utilities import neighbormanagement as nm
from scrapli.driver.core import AsyncIOSXEDriver, AsyncIOSXRDriver, AsyncNXOSDriver
from scrapli.logging import enable_basic_logging


class Netwalk:

    def __init__(self, seed, params):
        self.seed = seed
        self.params = params

        # init internal variables
        self.MAX_ATTEMPTS = 3
        self.visited_devices = set()
        self.visited_devices_names = set()
        self.hosts_with_errors = set()
        self.blacklisted_hosts = set()
        self.summary = []
        self.statistics = {}
        self.mappings = {}
        self.TEMPLATES_DIR = "./conf/textfsm/"

        enable_basic_logging(file=True, level="INFO")

    def write_inventory_to_disk(self, params):
        inventory = []
        filename = "%s/%s" % (params['output'], "inventory.yaml")
        print("writing data to %s" % filename)

        for host in self.summary:
            if host['polling'] != 'failure':
                inv = {'host': host['host'],
                    'hostname': host['hostname'],
                    'platform': host['platform']}
                inventory.append(inv)

        with open(filename, "w") as filehandler:
            filehandler.write(yaml.dump(inventory, default_flow_style=False))

    def write_data_to_disk(self, host, data, params):

        filename = "%s/%s%s" % (params['output'], host, params['postfix'])
        print ("writing data to %s" % filename)

        if not params['show_cdp']:
            if 'show cdp neighbors detail' in data:
                del data['show cdp neighbors detail']
            if 'show ip bgp neighbors' in data:
                del data['show ip bgp neighbors']

        if params['format'] == 'json':
            with open(filename, "w") as filehandler:
                filehandler.write(json.dumps(data, indent=4))
                filehandler.close()
        elif params['format'] == 'yaml':
            with open(filename, "w") as filehandler:
                filehandler.write(yaml.dump(data, default_flow_style=False))
                filehandler.close()
        elif params['format'] == "table":
            header = data[0].keys()
            rows = [x.values() for x in data]
            tab = tabulate.tabulate(rows, header)
            with open(filename, "w") as filehandler:
                filehandler.write(tab)
                filehandler.close()

    def print_dataset(self, host, result, params):

        if not params['show_cdp']:
            if 'show cdp neighbors detail' in result:
                del result['show cdp neighbors detail']
            if 'show ip bgp neighbors' in result:
                del result['show ip bgp neighbors']
            result["echo"] = {'host_ip': host, 'echo': True}

        output_format = params.get('format', 'json')
        if output_format == 'json':
            print(json.dumps(result, indent=4))
        elif output_format == "yaml":
            print(yaml.dump(resul))
        elif output_format == "table":
            # if the table was joined it is a list, otherwise a dict
            if isinstance(result, dict):
                try:
                    for key, values in result.items():
                            if len(values) > 0:
                                header = values[0].keys()
                                rows = [x.values() for x in values]
                                tab = tabulate.tabulate(rows, header)
                                print(tab)
                except Exception as exc:
                    print("got exception; fallback to json (dict)")
                    print(json.dumps(result, indent=4))
            else:
                try:
                    if len(result) > 0:
                        header = result[0].keys()
                        rows = [x.values() for x in result]
                        tab = tabulate.tabulate(rows, header)
                        print(tab)
                except Exception as exc:
                    print("got exception; fallback to json (not dict)")
                    print(json.dumps(result, indent=4))

    def join_values(self, origin, name1, name2, key1, key2) -> list:

        target = []
        for l1 in origin[name1]:
            for l2 in origin[name2]:
                v1 = l1.get(key1)
                v2 = l2.get(key2)
                if v1 == v2:
                    target.append(l1 | l2)
        return target

    def merge_tables(self, values, template_config, job) -> list:

        final_set = []
        template = {}

        for t in template_config:
            template[t['key']] = t['value']

        table1 = job['source'][0]['table']
        table2 = job['source'][1]['table']
        key1 = job['source'][0]['key']
        key2 = job['source'][1]['key']

        dataset = self.join_values(values, table1, table2, key1, key2)

        for v in dataset:
            t = {}
            for key, value in template.items():
                t[key] = v.get(value)
            final_set.append(t)

        return final_set

    async def send_commands(self, worker, commands, params, host_ip, platform="ios"):

        result = {}
        echo = False

        device = {
            'host': host_ip,
            'auth_username': params["auth_username"],
            'auth_password': params["auth_password"],
            "auth_strict_key": False,
            "transport": "asyncssh",
            "timeout_socket": 10,
            "timeout_transport": 10,
            "timeout_ops": 120,
            "ssh_config_file": "/etc/ssh/ssh_config",
            # "ssh_config_file": True
        }
        if host_ip not in self.statistics:
            self.statistics[host_ip] = dict(device)

        if platform == 'nxos':
            driver = AsyncNXOSDriver
        else:
            driver = AsyncIOSXEDriver

        # prepare commands to send to our device
        # remove echo, this is not a valid cisco command
        cmds = []
        for cmd in commands:
            if cmd == "echo":
                echo = True
            else:
                cmds.append(commands[cmd]['command'])

        try:
            logging.debug("(%s) connecting to %s (%s)" % (worker, host_ip, platform))
            async with driver(**device) as conn:
                logging.debug("(%s) successfully logged in to %s (%s)" % (worker, host_ip, platform))
                if len(cmds) > 0:
                    logging.debug("(%s) Sending %s commands to %s" % (worker, len(cmds), host_ip))
                    responses = await conn.send_commands(cmds)
                    logging.debug("(%s) successfully sent %s commands to %s" % (worker, len(cmds), host_ip))
                else:
                    if echo:
                        logging.debug("(%s) log echo for %s" % (worker, host_ip))
                        return True, {'echo': {'host_ip': host_ip, 'echo': True}}
                    else:
                        logging.debug("(%s) return {} for %s" % (worker, host_ip))
                        return False, {}
        except Exception as exc:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            message = "(%s) error got exception in line %s: %s (%s, %s, %s)" % (worker,
                                                                                exc_tb.tb_lineno,
                                                                                exc, exc_type,
                                                                                exc_obj,
                                                                                exc_tb)
            logging.error(message)
            return False, message

        # now parse the response of the commands
        for response in responses:
            channel_input = response.channel_input
            logging.debug("(%s) channel_input: %s" % (worker, channel_input))
            filename = "%s/%s" % (self.TEMPLATES_DIR, commands[channel_input]['template'][platform])
            try:
                template = open(filename)
                re_table = textfsm.TextFSM(template)
                fsm_results = re_table.ParseText(response.result)
                collection_of_results = [dict(zip(re_table.header, pr)) for pr in fsm_results]
                result[channel_input] = collection_of_results
            except Exception as exc:
                # this is an error while parsing not connecting
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logging.error("(%s) parser error in line %s; got: %s (%s, %s, %s)" % (worker,
                                                                            exc_tb.tb_lineno,
                                                                            exc,
                                                                            exc_type,
                                                                            exc_obj,
                                                                            exc_tb))
                result[channel_input] = "Parsing failed"

        return True, result

    async def async_worker(self, worker, queue, params):

        while True:
            q = await queue.get()
            if q['host_ip'] not in self.visited_devices and q['hostname'] not in self.visited_devices_names:
                logging.info("(%s) polling device: %s" % (worker, q['host_ip']))
                success, result = await self.send_commands(worker, params['commands'], params, q['host_ip'], q['platform'])
                if not success:
                    # increase error counter of device
                    if 'errors' in self.statistics[q['host_ip']]:
                        self.statistics[q['host_ip']]['errors'] = self.statistics[q['host_ip']]['errors'] + 1
                    else:
                        self.statistics[q['host_ip']]['errors'] = 1

                    if self.statistics[q['host_ip']]['errors'] < self.MAX_ATTEMPTS:
                        print("(%s) re-adding %s/%s to queue (cdp)" % (worker, q['host_ip'], q['platform']))
                        queue.put_nowait({'host_ip': q['host_ip'], 'hostname': q['hostname'], 'platform': q['platform']})
                        self.hosts_with_errors.add(q['host_ip'])
                        self.summary.append({'host': q['host_ip'],
                                             'hostname': q['hostname'],
                                             'platform': q['platform'],
                                             'polling': 'failure',
                                             'adding': "---"})
                    # task is done
                    queue.task_done()
                    continue

                # successfully logged in, remove from error list if present
                if q['host_ip'] in self.hosts_with_errors:
                    self.hosts_with_errors.remove(q['host_ip'])

                self.visited_devices.add(q['host_ip'])
                if q['hostname'] != 'unknown' and q['hostname'] != 'seed':
                    self.visited_devices_names.add(q['hostname'])

                # get neighbors and add them to queue
                for cmd in result:
                    hosts = set()
                    # set seed hostname if possible
                    if q['hostname'] == 'seed' and cmd == "show version":
                        q['hostname'] = result[cmd][0].get('HOSTNAME')

                    # check if we have cdp to parse
                    if params['walk'] and cmd == "show cdp neighbors detail":
                        neighbors, hosts = nm.get_cdp_neighbors(worker,
                                                                q,
                                                                result[cmd],
                                                                self.mappings,
                                                                self.visited_devices,
                                                                self.visited_devices_names,
                                                                self.blacklisted_hosts,
                                                                self.statistics,
                                                                hosts)
                        for neighbor in neighbors:
                            queue.put_nowait(neighbor)
                    # any BGP neighbor?
                    if params['walk'] and cmd == "show ip bgp neighbors":
                        neighbors, hosts = nm.get_bgp_neighbors(worker,
                                                                result[cmd],
                                                                self.mappings,
                                                                self.visited_devices,
                                                                self.blacklisted_hosts,
                                                                self.statistics,
                                                                hosts)
                        for neighbor in neighbors:
                            queue.put_nowait(neighbor)
                    # any static routes
                    if params['walk'] and cmd == "show ip route":
                        neighbors, hosts = nm.get_static_routing_neighbors(worker,
                                                                        result[cmd],
                                                                        self.mappings,
                                                                        self.visited_devices,
                                                                        self.blacklisted_hosts,
                                                                        self.statistics,
                                                                        hosts)
                        for neighbor in neighbors:
                            queue.put_nowait(neighbor)

                if 'join' in params:
                    result = self.merge_tables(result, params['join']['destination']['value'], params['join'])

                # save summary data
                if len(hosts) == 0:
                    added = "---"
                else:
                    added = ','.join(hosts)
                self.summary.append({'host': q['host_ip'],
                                     'hostname': q['hostname'],
                                     'platform': q['platform'],
                                     'polling': 'success',
                                     'adding': added})

                if params['job'] != "inventory":
                    if params['write']:
                        self.write_data_to_disk(q['host_ip'], result, params)
                    if params['print']:
                        self.print_dataset(q['host_ip'], result, params)

            else:
                logging.debug("Skipping %s (%s)" % (q['host_ip'], q['hostname']))
            # Notify the queue that the "work item" has been processed.
            queue.task_done()

    async def run(self):
        num_of_nodes = self.params['threads']
        logging.info("starting %s tasks" % num_of_nodes)

        # Create a queue that we will use to store our "workload".
        queue = asyncio.Queue()
        # put initial seed device in queue
        queue.put_nowait(self.seed)

        # Create worker tasks to process the queue concurrently.
        tasks = []
        for i in range(num_of_nodes):
            task = asyncio.create_task(self.async_worker(i, queue, self.params))
            tasks.append(task)

        # Wait until the queue is fully processed.
        await queue.join()

        # Cancel our worker tasks.
        for task in tasks:
            task.cancel()

        # Wait until all worker tasks are cancelled.
        await asyncio.gather(*tasks, return_exceptions=True)

        if self.params['job'] == "inventory":
            self.write_inventory_to_disk(self.params)

        # print self.statistics
        print("-============ Statistics ============-")
        runtime = time.time() - int(self.params['started'])
        print("Runtime: %d" % runtime)
        print("Hosts scanned: %s" % len(self.visited_devices))
        print("hosts with errors: %s" % len(self.hosts_with_errors))
        for host in self.hosts_with_errors:
            if host in self.statistics:
                errors = self.statistics[host].get('errors')
            print("host: %s errors: %s" % (host, errors))

        header = self.summary[0].keys()
        rows = [x.values() for x in self.summary]
        tab = tabulate.tabulate(rows, header)
        print(tab)
