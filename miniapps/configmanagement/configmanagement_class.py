from loguru import logger
import importlib
import veritas.plugin
import yaml
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
    def __init__(self):
        pass

    def load_plugin(self, package, subpackage):
        if not package or not subpackage:
            logger.error('no package or subpackage')
            return
        
        try:
            importlib.import_module(f'{package}.{subpackage}')
        except Exception as exc:
            logger.critical(f'failed to import plugin {package}.{subpackage}; got exception {exc}')

    def load_yaml_file(self, filename):
        try:
            with open(filename) as f:
                return yaml.safe_load(f.read())
        except Exception as exc:
            logger.error(f'could not read or parse config; got exception {exc}')
            return None

    def get_function_to_call(self, call):
        plugin = veritas.plugin.Plugin()
        func = plugin.get_orchestrator_plugin(call)
        if callable(func):
            return func
        else:
            logger.error(f'{call} is not callable')
            return None

    # tasks

    def download_config(self, task:Task, path:str, config_type:str = "running", 
                        set_timestamp:bool=False):

        dt = ""
        hostname = str(task.host)

        # Task 1. get configs from device
        logger.bind(extra=hostname).info('getting config')
        response = task.run(
            name="get_config",
            task=napalm_get, getters=['config'], retrieve="all"
        )
        running_config = response[0].result.get('config',{}).get('running')
        startup_config = response[0].result.get('config',{}).get('startup')

        # get current date and time
        if set_timestamp:
            now = datetime.now()
            dt = f'_{now.strftime("%Y_%m_%d_%H%M%S")}'

        # use individual host directories?
        prefix = f'{path}/{task.host}{dt}'

        # modify startup config
        # on some cisco switches the startup config begins with Using xx out of yy bytes
        if startup_config and startup_config.startswith('Using '):
            startup_config = startup_config.split('\n',1)[1]

        # replace ^C with etx(03)
        running_config = running_config.replace('^C', "\x03")
        startup_config = startup_config.replace('^C', "\x03")

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

    def send_commands_to_device(self, task:Task, commands, configure_device=False):
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

    def get_running_config(self, task:Task):
        response = task.run(
            name="get_running_config",
            task=napalm_get, getters=['config'], retrieve="all"
        )
        return response[0].result.get('config',{}).get('running')

    # configuring device

    def load_vars(self, task:Task, host_vars):
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
            running_config = self.get_running_config(task)
            parsed_config = configparser.Configparser(config=running_config, platform='ios')
            # the current config is added to the host vars
            task.host['vars']['current_config'] = {}
            for section in load.get('sections',[]):
                cfg = parsed_config.get_section(section)
                task.host['vars']['current_config'][section] = cfg

        return Result(host=task.host, changed=False, failed=False, result="loaded")

    def load_hooks(self, task:Task):
        host_vars = task.host['vars']
        hooks = host_vars.get('general',{}).get('hooks')
        if hooks:
            plugins = hooks.get('plugins',[])
            # load all plugins
            for plugin in plugins:
                logger.bind(extra="hooks").debug(f'loading plugin plugins.{plugin}')
                self.load_plugin('plugins',plugin)

    def run_preprocessing(self, task:Task):
        host_vars = task.host['vars']

        # run preprocessing plugin
        # the user can mofify the host_vars eg. scanning the running config and set
        # additional host_vars
        hooks = host_vars.get('general',{}).get('hooks',{})
        if hooks.get('preprocessing',False):
            call = hooks.get('preprocessing')
            logger.bind(extra="cfg device").debug(f'running plugin {call}')
            func = self.get_function_to_call(call)
            task.host['vars'] = func(host_vars=host_vars, host=task.host)
            host_vars = task.host['vars']

    def render_template(self, task:Task, template, path):
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

    def run_postprocessing(self, task:Task):
        host_vars = task.host['vars']

        # run postprocessing plugin
        # the user can mofify the the commands
        hooks = host_vars.get('general',{}).get('hooks',{})
        if hooks.get('postprocessing',False):
            call = hooks.get('postprocessing')
            logger.bind(extra="cfg device").debug(f'running plugin {call}')
            func = self.get_function_to_call(call)
            task.host['commands'] = func(host_vars=host_vars, commands=task.host['commands'])

    def configure_device(self, task:Task, dry_run=False):
        commands = task.host['commands']
        if dry_run:
            logger.bind(extra="cfg device").info('dry run, no changes will be made')
            logger.bind(extra="cfg device").info(f'commands: {commands}')
        elif len(commands) > 0:
            logger.bind(extra="cfg device").info(f'configuring {task.host}')
            task.run(task=self.send_commands_to_device, commands=commands, configure_device=True)

    def write_config(self, task):
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
