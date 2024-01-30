############
Installation
############

.. contents::

Brief overview
**************
This miniApp creates a minimal (but runnable) config for most of the miniApps.
There are two versions: a runnable python script and a jupyter notebook.

Basic configuration of the apps
*******************************

To create the config, you first have to add your values to config_values.yaml

.. code-block:: yaml

        ---
        nautobot:
            url: __nautobot_url__
            token: '__your_token__'
            ssl_verify: 'false'
        profile:
            username: __your_username__
            password: __your_encrypted_password__
            encryptionkey: __encryptionkey__
            salt: __secretsalt__
            iterations: 400000
        git:
            app_config:
                repo: sot_data
                path: '{HOMEDIR}/veritas/veritasData/miniapp_configs/'
            backup:
                repo: sot_data
                path: '{HOMEDIR}/veritas/veritasData/device_configs'
            config_context:
                repo: sot_data
                path: '{HOMEDIR}/veritas/veritasData/config_contexts'
            defaults:
                repo: sot_data
                path: '{HOMEDIR}/veritas/veritasData/'
                filename: defaults/default_values.yaml
            snmp_credentials:
                repo: sot_data
                path: '{HOMEDIR}/veritas/veritasData/'
                filename: defaults/credentials.yaml
        logging:
            to_database: 'false'
            to_rabbitmq: 'false'
            to_zeromq: 'false'
            uuid_to: rabbitmq
            database:
                database: journal
                host: 127.0.0.1
                port: 5672
                username: __db_username__
                password: __db_password__
            rabbitmq:
                host: 127.0.0.1
                port: 5672
            zeromq:
                host: 127.0.0.1
                port: 12345
                protocol: tcp
        #
        # App specific configs
        #
        messagebus:
            database:
                database: journal
                host: 127.0.0.1
                password: __db_username__
                username: __db_password__
        onboarding:
            default:
                interfaces: '["Loopback0", "Loopback100", "mgmt0"]'
        script_bakery:
            backup_dir: /tmp/backups
            git:
                backup:
                enabled: True
        sync_cmk:
            checkmk_password: __your_password__
            checkmk_site: cmk
            checkmk_url: __checkmk_url__
            checkmk_username: automation

.. note::

    The 'Profile password' must be encrypted before you add it to this config.
    Use the miniApp 
    
    .. code-block:: shell

        ./authentication/encrypt_password.py 
    
    to encrypt it. You will find a jupyter notebook ./encrypt_password.ipynb in the same directory.

Create config using the cmd
===========================

.. code-block:: shell

    usage: write_miniapp_configs.py [-h] [--config-values CONFIG_VALUES] [--basepath BASEPATH]

    options:
    -h, --help            show this help message and exit
    --config-values CONFIG_VALUES
                            read config values
    --basepath BASEPATH   basepath

Set the basepath to your need. The default value is '~user/.veritas/miniapps/'

Create config using Jupyter notebook
====================================

Open 

.. code-block:: shell

    >>> jupyter lab write_miniapp_configs.ipynb

to create your config. This notebook reads the config_values.yaml and creates the configs to 
your configured destination directory (default f'{HOMEDIR}/.veritas/miniapps/').

Basic configuration of the Database
***********************************

To install the database that is used to run the veritas journal:

.. code-block:: shell

    >>> ./installation/create_database_tables.py

The database configuration is read from the database_tables.yaml file. Customize the 
configuration and set host, user name and password according to your requirements.
