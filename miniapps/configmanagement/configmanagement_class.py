from loguru import logger
import importlib
import veritas.plugin
import yaml
from typing import Union, Tuple
from datetime import datetime
from nornir.core.task import Task, Result
from nornir_utils.plugins.tasks.data import load_yaml
from nornir_utils.plugins.tasks.files import write_file
from nornir_napalm.plugins.tasks import napalm_get
from nornir_jinja2.plugins.tasks import template_file
from nornir_scrapli.tasks import cfg_load_config, cfg_diff_config, cfg_commit_config
from nornir_netmiko.tasks import netmiko_save_config

# veritas
from veritas.configparser import cisco_configparser as configparser


class ConfigManagement():
    """ConfigManagement is a class to manage the configuration of network devices.
    """    
    def __init__(self):
        pass

    def load_plugin(self, package:str, subpackage:str) -> None:
        """load plugin using importlib

        Parameters
        ----------
        package : str
            package name
        subpackage : str
            subpackage name
        """        
        if not package or not subpackage:
            logger.error('no package or subpackage')
            return
        
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

    def load_yaml_file(self, filename:str) -> dict | None:
        """load yaml file from disk

        Parameters
        ----------
        filename : str
            filename

        Returns
        -------
        dict | None
            return dict containing the yaml file or None in case of an error
        """        
        try:
            with open(filename) as f:
                return yaml.safe_load(f.read())
        except Exception as exc:
            logger.error(f'could not read or parse config; got exception {exc}')
            return None

    def get_function_to_call(self, call:str) -> Union[callable, None]:
        """return function to call by its name

        Parameters
        ----------
        call : str
            name of the function to call

        Returns
        -------
        callable | None
            callable function or None in case of an error
        """        
        plugin = veritas.plugin.Plugin()
        func = plugin.get_configmanagement_plugin(call)
        if callable(func):
            return func
        else:
            logger.error(f'{call} is not callable')
            return None

    def get_section(self, content:str, section:str) -> list:
        """return section of the device configuration by name

        Parameters
        ----------
        content : str
            device configuration
        section : str
            name of the section

        Returns
        -------
        section : list
            section of the device configuration
        """        
        response = []
        if section == "interfaces":
            found = False
            for line in content.splitlines():
                # find first occurence of the word interface at the beginning of the line
                if line.lower().startswith('interface '):
                    found = True
                    response.append(line)
                    continue
                if found and line.startswith(' '):
                    response.append(line)
                else:
                    found = False
        else:
            for line in content.splitlines():
                # check if line begins with 'section'
                if line.lower().startswith(section):
                    response.append(line)

        return response

    # tasks

    def write_content_to_disk(self, task:Task, content:str, extra, filename:str) -> None:
        logger.bind(extra=extra).info(f'writing content to {filename}')
        task.run(
            name="write_content_{extra}",
            task=write_file,
            content=content,
            filename=filename
        )

    def get_config_from_device(self, task:Task, config_type:str = "running") -> str:

        running_config = None
        startup_config = None

        hostname = str(task.host)
        # Task 1. get configs from device
        retrieve = "all" if 'running' in config_type and 'startup' in config_type else config_type
        logger.bind(extra=hostname).info(f'getting {retrieve} config')
        response = task.run(
            name="get_config",
            task=napalm_get, getters=['config'], retrieve=retrieve
        )
        # get config from response
        if retrieve == "all":
            running_config = response[0].result.get('config',{}).get('running')
            startup_config = response[0].result.get('config',{}).get('startup')
            # replace ^C with etx(03)
            running_config = running_config.replace('^C', "\x03")
            startup_config = startup_config.replace('^C', "\x03")

            # modify startup config
            # on some cisco switches the startup config begins with Using xx out of yy bytes
            if startup_config.startswith('Using '):
                startup_config = startup_config.split('\n',1)[1]

            return running_config, startup_config
        elif retrieve == "running":
            running_config = response[0].result.get('config',{}).get('running')
            # replace ^C with etx(03)
            running_config = running_config.replace('^C', "\x03")
            return running_config
        elif retrieve == "startup":
            startup_config = response[0].result.get('config',{}).get('startup')
            # replace ^C with etx(03)
            startup_config = startup_config.replace('^C', "\x03")

            # modify startup config
            # on some cisco switches the startup config begins with Using xx out of yy bytes
            if startup_config.startswith('Using '):
                startup_config = startup_config.split('\n',1)[1]

            return startup_config

    def write_config_to_disk(self, task:Task, path:str, config_type:str = "running", 
                        set_timestamp:bool=False):
        """get config from device and save it to disk

        Parameters
        ----------
        task : Task
            the task object
        path : str
            path to save the config
        config_type : str, optional
            type of config to get, by default "running"
        set_timestamp : bool, optional
            add timestamp in filename, by default False
        """
        dt = ""
        startup_config = None
        running_config = None
        hostname = str(task.host)

        if 'running' in config_type and 'startup' in config_type:
            running_config, startup_config = self.get_config_from_device(task, 'all')
        if 'running' in config_type:
            running_config = self.get_config_from_device(task, 'running')
        elif 'startup' in config_type:
            startup_config = self.get_config_from_device(task, 'startup')

        # get current date and time
        if set_timestamp:
            now = datetime.now()
            dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'

        # use individual host directories?
        prefix = f'{path}/{task.host}{dt}'

        # Task 2. Write running config to file
        if 'running' in config_type:
            logger.bind(extra=hostname).info(f'writing running config to {path}')
            task.run(
                name="write_running_config",
                task=write_file,
                content=running_config,
                filename=f'{prefix}.running.cfg'
            )
        if 'startup' in config_type:
            logger.bind(extra=hostname).info(f'writing startup config to {path}')
            task.run(
                name="write_startup_config",
                task=write_file,
                content=startup_config,
                filename=f'{prefix}.startup.cfg'
            )

    def send_commands_to_device(self, task:Task, commands:list, configure_device:bool=False) -> Result:
        """send commands to device

        Parameters
        ----------
        task : Task
            the task object
        commands : list
            list of commands to send to the device
        configure_device : bool, optional
            use config mode when sending commands, by default False

        Returns
        -------
        result : Result
            the result of the task
        """        
        result = []
        # Manually create Netmiko connection
        try:
            net_connect = task.host.get_connection("netmiko", task.nornir.config)
            if configure_device:
                result.append({'cmd': 'config_mode', 'output': net_connect.config_mode()})
            for cmd in commands:
                # check if we have to confirm the command
                if '| confirm' in cmd:
                    cmd = cmd.replace('| confirm', '')
                    result.append({'cmd': cmd, 'output': net_connect.send_command(cmd, expect_string=r"confirm")})
                    result.append({'cmd': 'confirm', 'output': net_connect.send_command("y", expect_string=r"#")})
                else:
                    result.append({'cmd': cmd, 'output': net_connect.send_command(cmd, expect_string=r"#")})
            if configure_device:
                result.append({'cmd': 'exit_config_mode', 'output': net_connect.exit_config_mode()})
        except Exception as exc:
            result.append({'cmd': 'error', 'output': str(exc)})

        return Result(
            host=task.host,
            result=result
        )

    def get_config(self, task:Task, config_type="running") -> Union[Tuple[str, str], str]:
        """get running config from device

        Parameters
        ----------
        task : Task
            the task object

        Returns
        -------
        list(running_config, startup_config) or config : str
            the config(s) of the device
        """        
        response = task.run(
            name="get_config",
            task=napalm_get, getters=['config'], retrieve=config_type
        )
        if config_type == "all":
            return response[0].result.get('config',{}).get('running'),\
                   response[0].result.get('config',{}).get('startup'),
        else:
            return response[0].result.get('config',{}).get(config_type)

    # configuring device

    def load_vars(self, task:Task, host_vars:dict) -> Result:
        """load variables, additional YAML files and running config and add the values to the host

        Parameters
        ----------
        task : Task
            the task object
        host_vars : dict
            the host vars to use

        Returns
        -------
        Result
            result of the task
        """        
        logger.bind(extra="load_vars").debug('setting host variables')
        task.host['vars'] = host_vars

        # check if we need to load additional yaml files
        additional_yaml_files = host_vars.get('general',{}).get('load',{}).get('files',[])
        for key in additional_yaml_files:
            filename = additional_yaml_files[key]
            logger.bind(extra="load_vars").info(f'loading additional yaml file {filename} set to {key}')
            data = task.run(task=load_yaml, file=filename)
            task.host[key] = data.result

        # load running config if the user needs it
        load = host_vars.get('general',{}).get('load',{}).get('running_config',{})
        if load.get('load', False):
            logger.bind(extra="load_vars").info('loading running config')
            running_config = self.get_config(task, 'running')
            parsed_config = configparser.Configparser(config=running_config, platform='ios')
            # the current config is added to the host vars
            task.host['vars']['current_config'] = {}
            for section in load.get('sections',[]):
                cfg = parsed_config.get_section(section)
                task.host['vars']['current_config'][section] = cfg

        return Result(host=task.host, changed=False, failed=False, result="vars loaded")

    def load_hooks(self, task:Task) -> Result:
        """load hooks that are specified in the host_vars

        Parameters
        ----------
        task : Task
            the task object
        """        
        host_vars = task.host['vars']
        hooks = host_vars.get('general',{}).get('hooks')
        if hooks:
            plugins = hooks.get('plugins',[])
            # load all plugins
            for plugin in plugins:
                logger.bind(extra="hooks").debug(f'loading plugin plugins.{plugin}')
                self.load_plugin('plugins',plugin)

        return Result(host=task.host, changed=False, failed=False, result="hooks loaded")

    def run_preprocessing(self, task:Task) -> None:
        """run preprocessing plugin

        the preprocessing is called before the template rendering and the user can modify the host_vars
        eg. scanning the running config and set additional host_vars
        the arguments the preprocessing plugin gets are host_vars and task.host

        Parameters
        ----------
        task : Task
            the task object
        """        
        host_vars = task.host['vars']

        # run preprocessing plugin
        # the user can mofify the host_vars eg. scanning the running config and set
        # additional host_vars
        hooks = host_vars.get('general',{}).get('hooks',{})
        if hooks.get('preprocessing',False):
            call = hooks.get('preprocessing')
            logger.bind(extra="cfg device").debug(f'running plugin {call}')
            func = self.get_function_to_call(call)
            task.host['vars'] = func(task)
            host_vars = task.host['vars']

    def render_template(self, task:Task, template:str, path:str) -> None:
        """render template using jinja2

        Parameters
        ----------
        task : Task
            the task object
        template : str
            filename of the template
        path : str
            path to the template
        """        
        host_vars = task.host.get('vars',{})
        logger.bind(extra="render tmpl").debug(f'rendering template {template} for {task.host}')
        variables = dict(host_vars)
        variables.update(task.host.data)
        try:
            config_template = task.run(task=template_file, template=template, path=path, **variables)
            rendered_config = config_template.result
            task.host['commands'] = rendered_config.split('\n')
        except Exception as exc:
            logger.bind(extra="render tmpl").error(f'could not render template {template} for {task.host}; got exception {exc}')
            task.host['commands'] = []

    def run_postprocessing(self, task:Task) -> None:
        """run prostprocessing plugin

        run postprocessing plugin, the user can modify the commands before sending them to the device
        the arguments the postprocessing plugin gets are host_vars, task.host and commands

        Parameters
        ----------
        task : Task
            the task object
        """        
        host_vars = task.host['vars']

        # run postprocessing plugin
        # the user can mofify the the commands
        hooks = host_vars.get('general',{}).get('hooks',{})
        if hooks.get('postprocessing',False):
            call = hooks.get('postprocessing')
            logger.bind(extra="cfg device").debug(f'running plugin {call}')
            func = self.get_function_to_call(call)
            task.host['commands'] = func(task, commands=task.host['commands'])

    def configure_device(self, task:Task, dry_run=False):
        """configure device using the list of commands

        Parameters
        ----------
        task : Task
            the task object
        dry_run : bool, optional
            print commands if true, by default False
        """        
        commands = task.host['commands']
        if dry_run:
            logger.bind(extra="cfg device").info('dry run, no changes will be made')
            logger.bind(extra="cfg device").info(f'commands: {commands}')
        elif len(commands) > 0:
            logger.bind(extra="cfg device").info(f'configuring {task.host}')
            task.run(task=self.send_commands_to_device, commands=commands, configure_device=True)

    def write_config(self, task:Task) -> None:
        """write config to device

        Parameters
        ----------
        task : Task
            the task object
        """        
        # write config
        logger.bind(extra="cfg device").info('writing config')
        task.run(
            name="save_config",
            task=netmiko_save_config, 
        )

    # replace config

    def replace_config(self, task, path):
        hostname = str(task.host)
        with open(f'{path}/{hostname}.cfg', 'r') as file:
            configuration = file.read()
            # replace ^C with etx(03) ctrl-c
            # configuration = configuration.replace('^C', "\x03")

        logger.bind(extra=hostname).info(f'loading config to {task.host}')
        #task.run(task=napalm_configure, configuration=configuration, replace=True, dry_run=False)
        task.run(task=cfg_load_config, config=configuration, replace=True)
        logger.bind(extra=hostname).info('diffing config')
        task.run(task=cfg_diff_config, source="running")
        logger.bind(extra=hostname).info('committing config')
        task.run(task=cfg_commit_config, source="running")

    # intended config

    def render_intended_config(self, task):
        template = "ios.j2"
        path = "./templates/intended"

        host_vars = {'hostname': task.host.name}
        variables = dict(host_vars)
        variables.update(task.host.data)

        task.run(task=template_file, template=template, path=path, **variables)
        return Result(host=task.host, changed=False, failed=False, result="intended config rendered")
