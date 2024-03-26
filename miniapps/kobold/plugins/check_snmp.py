from loguru import logger
import yaml
import threading
from pysnmp.hlapi import (
    getCmd, SnmpEngine, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity, CommunityData,
    usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol, usmAesCfb128Protocol, usmAesCfb256Protocol, UsmUserData)
from pysnmp.smi.error import WrongValueError
from queue import Queue,  Empty

# veritas
from veritas.plugin import kobold
from veritas.tools import tools
import veritas.repo


processed_devices = 0
number_of_devices = 0

class Worker(threading.Thread):
    def __init__(self, threadnumber, sot, credentials, queue, *args, **kwargs):
        self.thread_number = threadnumber
        self.queue = queue
        self.sot = sot
        self.credentials = credentials
        super().__init__(*args, **kwargs)

    def try_to_connect(self, auth, device, community=None, port=161):

        if auth:
            iterator = getCmd(
                SnmpEngine(),
                auth,
                UdpTransportTarget((device, port)),
                ContextData(),
                ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysName', 0))
            )
        else:
            iterator = getCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((device, port)),
                ContextData(),
                ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysName', 0))
            )

        try:
            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        except WrongValueError:
                logger.error('WrongValueError... maybe your password/privacy is to short!')
                return False
        except Exception:
            return False

        if errorIndication:
            logger.error(f'({self.thread_number}) {errorIndication}')
            return False
        elif errorStatus:
            logger.error('(%s) %s at %s' % (self.thread_number, 
                                             errorStatus.prettyPrint(), 
                                             errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            return False
        else:
            for varBind in varBinds:
                pass
                # logger.debug(' = '.join([x.prettyPrint() for x in varBind]))
            return True

    def check_device(self, credentials, device):
        global number_of_devices
        global processed_devices

        processed_devices += 1
        hostname = device.get('hostname')
        address = device.get('host')

        logger.info(f'({self.thread_number}) checking {hostname} ({processed_devices}/{number_of_devices})')
        # iterate though SNMP credentials
        for credential in credentials.get('snmp'):
            connected = False
            snmp_id = credential.get("id")
            if credential.get('version') != 3:
                connected = self.try_to_connect(None, address, credential.get('community'), 161)
            else:
                cred = {'userName': credential.get('security_name')}
                if 'auth_password' in credential:
                    cred.update({'authKey': credential.get('auth_password')})
                if 'privacy_password' in credential:
                    cred.update({'privKey': credential.get('privacy_password')})
                if 'auth_protocol' in credential:
                    ap = credential.get('auth_protocol')
                    if ap.upper() in {'MD5', 'MD5-96'}:
                        cred.update({'authProtocol': usmHMACMD5AuthProtocol})
                    if ap.upper() in {'HMAC-SHA1-96',  'SHA1-96'}:
                        cred.update({'authProtocol': usmHMACSHAAuthProtocol})
                if 'privacy_protocol' in credential:
                    pp = credential.get('privacy_protocol')
                    if pp.upper() in {'AES-128', 'AES128'}:
                        cred.update({'privProtocol': usmAesCfb128Protocol})
                    if pp.upper() in {'AES-256'}:
                        cred.update({'privProtocol': usmAesCfb256Protocol})
                auth = UsmUserData(**cred)
                connected = self.try_to_connect(auth, address, 161)

            if connected:
                logger.info(f'({self.thread_number}) SNMP connected; snmp-id is {snmp_id}; updating device {hostname} in SOT')
                self.sot.device(hostname).update({'custom_fields': {'snmp_credentials': snmp_id}})
                break
            else:
                logger.debug(f'({self.thread_number}) connection failed or {snmp_id}; trying next credentials')

    def run(self):
        while True:
            try:
                device = self.queue.get(timeout=3)
                logger.debug(f'processing {device["hostname"]}')
            except Empty:
                return
            # do whatever work you have to do on work
            self.check_device(self.credentials, device)
            self.queue.task_done()

def read_snmp_credentials(sot, name_of_repo, path_to_repo, filename):
    # get SNMP credentials from SOT
    logger.debug(f'loading SNMP credentials from {path_to_repo}/{filename}')
    repo = veritas.repo.Repository(repo=name_of_repo, path=path_to_repo)
    snmp_credentials_text = repo.get(filename)
    return yaml.safe_load(snmp_credentials_text)

@kobold("check_snmp_credentials")
def check_snmp_credentials(*args, **kwargs):
    properties = tools.convert_arguments_to_properties(args, kwargs)

    sot = properties.get('sot')
    arguments = properties.get('arguments')
    devices = properties.get('devices')

    # get values from task
    threads = arguments.get('threads', 2)
    update = arguments.get('update', False)
    use = arguments.get('use', [])
    excluded = arguments.get('excluded',{})
    name_of_repo = arguments.get('repo_name')
    path_to_repo = arguments.get('repo_path')
    filename_repo = arguments.get('repo_filename')

    nn_hosts = 0
    skipped = 0
    devicelist = []
    logger.debug(f'got {len(devices)} device(s) from sot')
    for device in devices:
        host = {'hostname': device.get('hostname')}
        hostname = device.get('hostname')
        for e in excluded:
            if e in host:
                logger.debug(f'host {device} excluded due to parameter')
                skipped += 1
                continue
        if 'primary_ip4' in device and device['primary_ip4'] and 'address' in device['primary_ip4']:
            host['host'] = device.get('primary_ip4').get('address').split('/')[0]
        else:
            logger.error(f'device {device} has no primary_ip in SOT')
            continue
        if 'platform' in device and device['platform']:
            host['platform'] = device.get('platform',{}).get('name')
        else:
            logger.error(f'invalid platform of host {hostname}')
            host['platform'] = "unknown"
        if not update:
            dev_cred = device.get('custom_field_data',{}).get('snmp_credentials')
            if dev_cred is not None and dev_cred.lower() != 'unknown' and len(dev_cred) > 0:
                logger.debug(f'host {hostname} has active SNMP credentials')
                skipped += 1
                continue
        devicelist.append(host)
        nn_hosts += 1
        logger.debug(f'adding {hostname} / plattform: {host["platform"]}')

    if nn_hosts == 0:
        logger.info(f'added {nn_hosts} to our list of devices; skipped {skipped} devices')
        print('device list is empty; we have nothing to do')
        return

    if use and use != 'None' and len(use) > 0:
        used = use.split(',')
        credentials = {'snmp': []}
        for cred in read_snmp_credentials(sot, name_of_repo, path_to_repo, filename_repo)['snmp']:
            if cred['id'] in used:
                credentials['snmp'].append(cred)
    else:
        credentials = read_snmp_credentials(sot, name_of_repo, path_to_repo, filename_repo)

    queue = Queue()
    for device in devicelist:
        queue.put_nowait(device)
    
    for i in range(threads):
        Worker(i, sot, credentials, queue).start()
    queue.join()
