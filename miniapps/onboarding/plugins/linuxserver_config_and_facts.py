from loguru import logger
import paramiko

# veritas
from veritas.onboarding import plugins


@plugins.config_and_facts('linux')
def get_device_config_and_facts(device_ip, device_defaults, profile, tcp_port=22, scrapli_loglevel='none'):

    device_config = {'fqdn': '',
                     'interfaces': {}}
    device_facts = {'fqdn':''}

    client = paramiko.client.SSHClient()
    # validate the trust with the machine for the first time we try to connect to the server
    # use set_missing_host_key_policy() to add the key automatically
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.load_system_host_keys()
    if profile.ssh_key:
        logger.debug(f'connecting to {device_ip} using ssh_key')
        client.connect(
            device_ip, 
            username=profile.username,
            look_for_keys=True,
            key_filename=profile.ssh_key,
            passphrase=profile.ssh_passphrase)
    else:
        logger.debug(f'connecting to {device_ip} using username/password')
        client.connect(
            device_ip,
            username=profile.username,
            password=profile.password)

    # get hostname
    _stdin, _stdout,_stderr = client.exec_command("hostname")
    device_config['fqdn'] = _stdout.read().decode()
    device_facts['fqdn'] = _stdout.read().decode()

    # get ip addresses
    _stdin, _stdout,_stderr = client.exec_command("ip a")
    device_config['interfaces'] = _stdout.read().decode()

    logger.debug(f'Return code: {_stdout.channel.recv_exit_status()}')
    client.close()

    return device_config, device_facts
