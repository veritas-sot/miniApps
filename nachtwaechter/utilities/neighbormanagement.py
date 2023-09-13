
def get_cdp_neighbors(worker, q, result, mappings, visited_devices, \
                      visited_devices_names, blacklisted_hosts, statistics, hosts):
    neighbors = []
    MAX_ATTEMPTS = 3

    for line in result:
        host = line.get('MANAGEMENT_IP')
        if host is None or host == "":
            host = line.get('INTERFACE_IP')
        if host is None or host == "":
            print("(%s) could either parse MANAGEMENT_IP nor INTERFACE_IP on %s" % (worker, q['host_ip']))
            break
        software = line.get('SOFTWARE_VERSION')
        hostname = line.get('DESTINATION_HOST')
        # check if mapping exists
        if host in mappings:
            host = mappings[host]
        elif hostname in mappings:
            host = mappings[hostname]
        if software is not None and ('NXOS' in software or 'NX-OS' in software):
            platform = "nxos"
        elif software is not None and 'IOS' in software:
            platform = "ios"
        else:
            # eg VMWare ESXi (switch)
            print("unknown neighbor platform - %s/%s - on %s" % (software, host, q['host_ip']))
            break
        if host not in hosts and \
                host not in visited_devices and \
                hostname not in visited_devices_names and \
                host not in blacklisted_hosts:
            # check if we have a maximum number of attempts reached
            errors = 0
            if host in statistics:
                errors = statistics[host].get('errors', 0)
            if errors < MAX_ATTEMPTS:
                hosts.add(host)
                print("(%s) adding %s/%s to queue (cdp)" % (worker, host, platform))
                neighbors.append({'host_ip': host, 'hostname': hostname, 'platform': platform})

    return neighbors, hosts

def get_bgp_neighbors(worker, result, mappings, visited_devices, blacklisted_hosts, statistics, hosts):
    neighbors = []
    MAX_ATTEMPTS = 3

    for line in result:
        host = line['REMOTE_IP']
        # check if mapping exists
        if host in mappings:
            host = mappings[host]

        platform = "ios"
        if host not in hosts and \
                host not in blacklisted_hosts and \
                host not in visited_devices and \
                host != "0.0.0.0":
            # check if we have a maximum number of attempts reached
            errors = 0
            if host in statistics:
                errors = statistics[host].get('errors', MAX_ATTEMPTS)
            if errors < MAX_ATTEMPTS:
                hosts.add(host)
                print("(%s) adding %s/%s to queue (bgp)" % (worker, host, platform))
                neighbors.append({'host_ip': host, 'hostname': 'unknown', 'platform': platform})

    return neighbors, hosts

def get_static_routing_neighbors(worker, result, mappings, visited_devices, blacklisted_hosts, statistics, hosts):
    neighbors = []
    MAX_ATTEMPTS = 3
    
    for line in result:
        host = line['NEXTHOP_IP']
        # check if mapping exists
        if host in mappings:
            host = mappings[host]

        platform = "ios"
        if host not in hosts and \
                host not in blacklisted_hosts and \
                host not in visited_devices and \
                host != "0.0.0.0":
            # check if we have a maximum number of attempts reached
            errors = 0
            if host in statistics:
                errors = statistics[host].get('errors', MAX_ATTEMPTS)
            if errors < MAX_ATTEMPTS:
                hosts.add(host)
                print("(%s) adding %s/%s to queue (route)" % (worker, host, platform))
                neighbors.append({'host_ip': host, 'hostname': 'unknown', 'platform': platform})

    return neighbors, hosts
