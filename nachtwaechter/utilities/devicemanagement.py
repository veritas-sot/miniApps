from scrapli import Scrapli


def open_connection(host, username, password, platform, port=22):

    """
        open connection to a device

    Args:
        host:
        username:
        password:
        platform:

    Returns:

    """

    # we have to map the napalm driver to our srapli driver / platform
    #
    # napalm | scrapli
    # -------|------------
    # ios    | cisco_iosxe
    # iosxr  | cisco_iosxr
    # nxos   | cisco_nxos

    mapping = {'ios': 'cisco_iosxe',
               'iosxr': 'cisco_iosxr',
               'nxos': 'cisco_nxos'
               }
    driver = mapping.get(platform)
    if driver is None:
        return None

    device = {
        "host": host,
        "auth_username": username,
        "auth_password": password,
        "auth_strict_key": False,
        "platform": driver,
        "port": port,
        "ssh_config_file": "~/.ssh/ssh_config"
    }

    conn = Scrapli(**device)
    conn.open()

    return conn


def get_config(conn, configtype: str) -> str:
    """
    return config from device

    Args:
        conn:
        configtype:

    Returns:
        config: str
    """

    response = conn.send_command("show %s" % configtype)
    return response.result

