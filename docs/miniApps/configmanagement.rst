################
Configmanagement
################

.. contents::

**************
Brief overview
**************
With the 'configmanagement' MiniApp you can manage the configuration of your device. 
The functions are as follows:

    - Download running and startup configuration
    - Upload running configuration
    - Modify the running configuration using jinja2 templates
    - Render the intended configuration using jinja2 templates

**********
Let it run
**********
.. code-block:: shell

        usage: config.py [-h] [--config CONFIG] [--loglevel LOGLEVEL] [--loghandler LOGHANDLER] 
                         [--uuid UUID] --devices DEVICES [--username USERNAME] [--password PASSWORD] 
                         [--profile PROFILE] [--port PORT]
                        {get,deploy,replace,context} ...

        positional arguments:
        {get,deploy,replace,context}
            get                 download device configs or render intended config
            deploy              configure devices using templates
            replace             replace existing config on device with new config
            context             get and set config context

        options:
        -h, --help            show this help message and exit
        --config CONFIG       used config file
        --loglevel LOGLEVEL   used loglevel
        --loghandler LOGHANDLER
                                used log handler
        --uuid UUID           database logger uuid
        --devices DEVICES     IP or name of device
        --username USERNAME
        --password PASSWORD
        --profile PROFILE
        --port PORT           TCP Port to connect to device

As you can see there are four commands you can use: get, deploy, replace and cotext

All of the commands have their own help page, which you can access by typing the command and then --help.
Common options for all commands are setting the loglevel, loghandler, uuid, devices, profile (or username and 
password) and port.

***
get
***

.. code-block:: shell

        usage: config.py get [-h] [--running] [--startup] [--intended] [--set-timestamp] [--directory DIRECTORY] [--section [SECTION ...]] [--output OUTPUT]

        options:
        -h, --help            show this help message and exit
        --running             get running config
        --startup             get startup config
        --intended            render intended config
        --set-timestamp       set timestamp in filename
        --directory DIRECTORY
                                directory to save config to
        --section [SECTION ...]
                                get specific section of config
        --output OUTPUT       print or write to file

The options are mostly self-explanatory. If you just want a part of a configuration (e.g. only the interfaces),
you can use the parameter section. If you want to save the configuration to a file, you can use the parameter 'output=write-file'
or just skip the option, because this is the default value. To print the configuration to the console, use 'output=sysout'.

The intended configuration is the configuration that would be applied to the device. It is rendered on the fly.
The templates can be found in the 'templates/intended' directory.

******
deploy
******

.. code-block:: shell

        usage: config.py deploy [-h] [--vars VARS] [--path PATH] --template TEMPLATE [--dry-run]

        options:
        -h, --help           show this help message and exit
        --vars VARS          host variables to use
        --path PATH          path where to find templates
        --template TEMPLATE  template to use
        --dry-run            Make no changes, just print

The deploy command is used to configure the device using jinja2 templates. The templates can be found in the 'templates/jobs' 
directory. The host variables are stored in the 'host_vars' directory. The path to the templates can be set using the 
parameter 'path' whereas the name of the template is configured using the 'template' parameter.

To extend the functionality of the deploy command, you can use the 'hooks' parameter in the host_vars file. The plugin
is loaded when you start the miniApp. The preprocessing is executed after the host_vars file is loaded and before the template
is rendered. The postprocessing is executed after the template is rendered and before the configuration is deployed.

The structure of a host_var file is as follows:

.. code-block:: yaml

        ---
        general:
        load:
            running_config:
            load: true
            sections:
                - username
        hooks:
            plugins:
            - username_handling
            # we add no username commands to the list of commands to be executed
            postprocessing: postprocessing
        aaa: 
          users:
            - username: lab
            privilege: 15
            secret: lab
            - username: anotheruser
            privilege: 15
            secret: anotherpassword

The host_vars (in the example above the 'aaa' variable including its 'child' variable) are passed to the jinja2 template 
and can be used in the template. The templates are rendered on the fly and the configuration is deployed to the device.
The templates can be found in the 'templates/deploy' directory. An example template is as follows:

.. code-block:: jinja

        {% for user in aaa["users"] %}
        username {{ user["username"] }} privilege {{ user["privilege"] }} secret {{ user["secret"] }}
        {% endfor %}

A pre/post-processing plugin is a python file that is located in the 'plugins/' directory. To tell the miniApp to use the plugin,
use the decorator '@preprocessing' and '@postprocessing' for the pre/post-processing plugin. 

Let's have a look at an example to illustrate the usage of the plugin (snmp_handling.py):

.. code-block:: python

        from loguru import logger

        # veritas
        from veritas.plugin import configmanagement


        @configmanagement("preprocessing")
        def preprocessing(task):
            logger.debug('preprocessing called...')

            host_vars = task.host['vars']

            snmp = {}
            snmp_credentials = task.host.get('snmp_credentials',[])
            for cred in task.host.get('credentials',{}).get('snmp',[]):
                if cred.get('id') == snmp_credentials:
                    snmp = dict(cred)
            if snmp:
                logger.bind(extra="preproc").debug(f'found snmp credentials {snmp_credentials}')
                host_vars['snmp'] = snmp

            return host_vars

        @configmanagement("postprocessing")
        def postprocessing(task, commands:list=[]):
            logger.debug('postprocessing called...')

            host_vars = task.host['vars']

            old_config = host_vars.get('current_config', {}).get('snmp-server',[])
            remove = []
            for cmd in old_config:
                remove.append('no ' + cmd)
            if len(remove) > 0:
                logger.info('removing old SNMP config')
                logger.debug(f'sending {remove}')
                return remove + commands
            else:
                return commands

As you can see the preprocessing plugin is used to add the snmp credentials to the host_vars. The postprocessing plugin is used
to remove the old snmp configuration from the device. It returns the commands to be executed on the device.

*******
replace
*******

.. code-block:: shell

        usage: config.py replace [-h] [--directory DIRECTORY]

        options:
        -h, --help            show this help message and exit
        --directory DIRECTORY
                                directory to load config from

*******
context
*******

.. code-block:: shell

        usage: config.py context [-h] [--get] [--set] [--update] [--config-from-disk] 
                                 [--config-dir CONFIG_DIR] [--template-dir TEMPLATE_DIR]

        options:
        -h, --help            show this help message and exit
        --get                 show config context
        --set                 set config context in SOT
        --update              update config context in SOT
        --config-from-disk    use file instead of getting config from device
        --config-dir CONFIG_DIR
                                directory to load configs from
        --template-dir TEMPLATE_DIR
                                directory to get config context from

The context command is used to get, set, and update the configuration context. 'set' overwrites the existing config context 
of the device whereas 'update' merges the existing context and the new one.
The configuration context is used to store the configuration of the device that is not part of the "standard" 
nautobot data model. The configuration context is used to render some parts of the intended configuration. The templates 
used to get the config context are stored in the 'config_context' directory. 

The next block is an example to show how to use a yaml file to generate a config context.

.. code-block:: yaml

        ---
        active: True
        name: ntp
        platform: ios
        source:
          fullconfig: True
        remove_empty: True
        template: |2
          <group name="ntp">
          ntp server {{ ip | _start_ }} {{ prefer | let("prefer", True) }}
          ntp server {{ ip | _start_ }}
          </group>

The template is used only if active is set to true. The platform must match the platform of the device. 
You can use the source parameter to get a specific part of the config or 'fullconfig: true' to use the 
full config. If the argument remove_empty is set to true empty variables are removed from the config context.
The template is then used to get the config context of a device. The outcome of the rendered template is used as 
config context.
