from loguru import logger
import yaml
import re
from benedict import benedict


class Playbook(object):

    def __init__(self, sot, playbook):
        self._jobs = {}
        self._playbook = self.read_playbook_config(playbook)
        self._sot = sot
        self._username = None
        self._password = None
        self._tcp_port = 22

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

    @property
    def jobs(self) -> str:
        """returns jobs"""       
        return self._jobs

    @property
    def username(self) -> str:
        """returns username"""       
        return self._username

    @username.setter
    def username(self, username):
        self._username = username

    @property
    def password(self) -> str:
        """returns password"""       
        return self._password
    
    @password.setter
    def password(self, password):
        self._password = password

    def get_jobs(self):
        return self._jobs

    @property
    def tcp_port(self) -> str:
        """returns tcp_port"""       
        return self._tcp_port

    @tcp_port.setter
    def username(self, tcp_port):
        self._tcp_port = tcp_port

    def pattern_to_filename(self, pattern, data):
        logger.debug(f'getting filename from {pattern}')
        
        final_path = []
        separator = re.compile(".*?__(.*?)__.*?")
        hldm = benedict(data, keyattr_dynamic=True)

        path = pattern.split('/')
        logger.debug(f'list of path={path}')

        for item in path:
            if '__' not in item:
                final_path.append(item)
                continue

            match = separator.match(item)
            if match:
                key = match.group(1)
                if key.startswith('cf_'):
                    custom_fields = hldm['custom_field_data']
                    try:
                        value = custom_fields[key.replace('cf_','')].replace(' ','_').replace('/','_')
                        final_item = item.replace(f'__{key}__', value)
                        logger.debug(f'key={key} value={final_item}')
                        final_path.append(final_item)
                    except Exception:
                        logger.error(f'unknown key {key}')
                else:
                    try:
                        value = hldm[key]
                        final_item = item.replace(f'__{key}__', value)
                        logger.debug(f'key={key} value={final_item}')
                        final_path.append(final_item)
                    except Exception:
                        logger.error(f'unknown key {key}')

        final_pattern = '/'.join(final_path)
        logger.debug(f'final pattern={final_pattern}')
        return final_pattern
