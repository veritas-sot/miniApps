import yaml
import json
import getpass
import os
import export
from loguru import logger


class Kobold(object):

    def __init__(self, sot, playbook):
        self._sot = sot
        self._playbook = None
        self._jobs = {}
        self._username = None
        self._password = None
        self._tcp_port = 22
        self._scrapli_loglevel = "error"
        self.read_playbook_config(playbook)
    
    def read_playbook_config(self, playbook):
        # load playbook
        logger.debug(f'reading playbook {playbook}')
        with open(playbook) as f:
            try:
                self._playbook = yaml.safe_load(f.read())
            except Exception as exc:
                raise Exception (f'could not parse yaml file {playbook}; got {exc}')
        
        for job in self._playbook.get('jobs',{}):
            self._jobs[job['job']] = job

    def set_profile(self, username=None, password=None):
        self._username = username
        self._password = password

    def set_tcp_port(self, port):
        self._tcp_port = port

    def set_scrapli_loglevel(self, loglevel):
        self._scrapli_loglevel = loglevel

    def get_username_and_password(self):
        """return username and password"""
        return self._username, self._password

    def get_tcp_port(self):
        return self._tcp_port

    def get_scrapli_loglevel(self):
        return self._scrapli_loglevel

    def get_jobs(self):
        return self._jobs

    def get_mapping(self):
        return []

    # certain jobs

    def tag_management(self, task, device_list):
        scope = task.get('scope')
        configured_tags = task.get('tag', [])
        if isinstance(configured_tags, str):
            tags = [ configured_tags ]
        else:
            tags = configured_tags
        if scope is None or len(tags) == 0:
            logger.error(f'scope and tags must be configured to set tags')
            return
        for device in device_list:
            hostname = device.get('hostname')
            if scope == "dcim.interface":
                for interface in device.get('interfaces', []):
                    interface_name = interface.get('name')
                    if 'add_tag' in task:
                        logger.info(f'adding tag {tags} on {hostname}/{interface_name}')
                        self._sot.device(hostname).interface(interface_name).add_tags(tags)
                    elif 'set_tag' in task:
                        logger.info(f'setting tag {tags} on {hostname}/{interface_name}')
                        self._sot.device(hostname).interface(interface_name).set_tags(tags)
                    elif 'delete_tag':
                        logger.info(f'deleting tag {tags} on {hostname}/{interface_name}')
                        self._sot.device(hostname).interface(interface_name).delete_tags(tags)
            elif scope == "dcim.device":
                if 'add_tag' in task:
                    logger.info(f'add tag {tags} on {hostname}')
                    self._sot.device(hostname).add_tags(tags)
                elif 'set_tag' in task:
                    logger.info(f'setting tag {tags} on {hostname}')
                    self._sot.device(hostname).set_tags(tags)
                elif 'delete_tag' in task:
                    logger.info(f'deleting tag {tags} on {hostname}')
                    self._sot.device(hostname).delete_tags(tags)

    def custom_field(self, task, device_list):
        custom_fields = task.get('custom_field')
        for device in device_list:
            hostname = device.get('hostname')
            device_scope = {}
            interface_scope = {}
            # custom_fields is the list of custom_fields to update
            for properties in custom_fields:
                prop = dict(properties)
                scope = prop.get('scope')
                del prop['scope']
                if scope == "dcim.device":
                    logger.info(f'setting custom field {prop} on {hostname}')
                    device_scope.update(prop)
                elif scope == "dcim.interface":
                    for interface in device.get('interfaces', []):
                        interface_name = interface.get('name')
                        logger.info(f'setting custom field {prop} on {hostname}/{interface_name}')
                        if interface_name not in interface_scope:
                            interface_scope[interface_name] = {}
                        interface_scope[interface_name].update(prop)

            logger.debug(f'adding device scope custom fields to {hostname}')
            if len(device_scope) > 0:
                success = self._sot.device(hostname).set_customfield({'custom_fields': device_scope})
                if success:
                    logger.info(f'device custom field updated on {hostname}')
                else:
                    logger.error(f'could not set custom field on {hostname}')

            for interface in interface_scope:
                logger.debug(f'adding interface scope custom fields to {hostname}/{interface}')
                success = self._sot.device(hostname) \
                              .interface(interface) \
                              .set_customfield({'custom_fields': interface_scope[interface]})
                if not success:
                    logger.error(f'could not set custom field on {hostname}/{interface}')

    def update_device(self, task, device_list):
        for device in device_list:
            hostname = device.get('hostname', device.get('name'))
            properties = task.get('update_device')
            logger.debug(f'updating {hostname}')
            success = self._sot.device(hostname).update(properties)
            if success:
                logger.info(f'updated {hostname} successfully')
            else:
                logger.info(f'could not update {hostname}')

    def update_interface(self, task, device_list):
        for device in device_list:
            hostname = device.get('hostname', device.get('name'))
            properties = task.get('update_interface',{})
            for interface in device.get('interfaces', []):
                interface_name = interface.get('name')
                logger.debug(f'updating {hostname}/{interface_name}')
                success = self._sot.device(hostname) \
                                   .interface(interface_name) \
                                   .update(properties)
                if success:
                    logger.info(f'updated {hostname}/{interface_name} successfully')
                else:
                    logger.info(f'could not update {hostname}/{interface_name}')

    # the main RUN command

    def run(self, job_id):
        job = self._jobs.get(job_id)
        if not job:
            logger.error(f'unknown job {job_id}')
            return False

        name = job.get('job')
        description = job.get('description','no description')
        logger.info(f'starting job {name} / {description}')

        if 'sql' in job.get('devices',{}):
            sql = job.get('devices').get('sql')
            device_list = self._sot.select(sql.get('select')) \
                                   .using(sql.get('from'), sql.get('using')) \
                                   .where(sql.get('where'))
            logger.debug(f'got {len(device_list)} devices')
        tasks = job.get('tasks')
        if tasks is None:
            logger.error(f'no task configured!!!')
            return False

        for task in tasks:
            if 'export' in task:
                export.export(self, self._sot, task['export'], device_list)
            if 'add_tag' in task or 'set_tag' in task or 'delete_tag' in task:
                self.tag_management(task, device_list)
            if 'custom_field' in task:
                self.custom_field(task, device_list)
            if 'update_device' in task:
                self.update_device(task, device_list)
            if 'update_interface' in task:
                self.update_interface(task, device_list)

