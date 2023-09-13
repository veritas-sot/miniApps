import json
import phpypam
import logging
from pynautobot import api
from phpypam.core.exceptions import PHPyPAMEntityNotFoundException, PHPyPAMException
from ipaddress import IPv4Network

class Phpipam(object):

    def __init__(self, url, app_id, username, password, ssl_verify):
        self._all_subnets = None
        self.sections_by_name = None
        self._pi = phpypam.api(url=url,
                               app_id=app_id,
                               username=username,
                               password=password,
                               ssl_verify=ssl_verify)

    def get_sections_from_phpipam(self):
        sections_by_name = {}
        sections_by_id = {}

        # get all sections
        all_sections = self._pi.get_entity(controller='sections', controller_path='/')
        if all_sections is not None:
            for section in all_sections:
                section_name = section['name']
                logging.debug(f'got section {section_name} from PHPIPAM')
                sections_by_name[section_name] = {'id': section['id'],
                                                  'name': section_name,
                                                  'description': section['description'],
                                                  'masterSection': section['masterSection']
                                                 }
                sections_by_id[section['id']] = {'id': section['id'],
                                                 'name': section_name,
                                                 'description': section['description'],
                                                 'masterSection': section['masterSection']
                                                }                                     

        return sections_by_id, sections_by_name

    def get_prefixe_from_phpipam(self, prefix):
        subnets = {}
        if prefix == "0.0.0.0/0":
            cp = "/"
        else:
            cp = "/search/%s" % prefix
        try:
            all_subnets = self._pi.get_entity(controller='subnets', controller_path='%s' % cp)
            logging.debug("found subnets; parsing")
            for subnet in all_subnets:
                cidr = "%s/%s" % (subnet['subnet'], subnet['mask'])
                logging.debug(f'prefix {cidr} is in PHPIPAM ({subnet.get("sectionId")})')
                subnets[cidr] = {'subnet': subnet['subnet'],
                                 'mask': subnet['mask'],
                                 'description': subnet['description'],
                                 'section_id': subnet['sectionId'],
                                 'master_subnet_id': subnet['masterSubnetId']}
        except (PHPyPAMEntityNotFoundException, PHPyPAMException) as exc:
            logging.info(f'no subnets for prefix {prefix} found; looking into details now')
            supernet = IPv4Network(prefix, strict=False)
            try:
                all_subnets = self._pi.get_entity(controller='subnets', controller_path='/')
                for subnet in all_subnets:
                    cidr = "%s/%s" % (subnet['subnet'], subnet['mask'])
                    net = IPv4Network(cidr, strict=False)
                    if net.subnet_of(supernet):
                        logging.debug(f'adding  {cidr} to subnets')
                        subnets[cidr] = {'subnet': subnet['subnet'],
                                        'mask': subnet['mask'],
                                        'description': subnet['description'],
                                        'section_id': subnet['sectionId'],
                                        'master_subnet_id': subnet['masterSubnetId']}
            except (PHPyPAMEntityNotFoundException, PHPyPAMException) as exc:
                logging.info("no subnets found for %s" % prefix)

        return subnets

    def add_section_to_phpipam(self, name, description, parent, all_sections):
        my_section = {
            'name': name,
            'description': description,
            'permissions': '{"2":"2","3":"2","4":"2"}'
        }

        if parent in all_sections:
            logging.debug('found parent in sections; using masterSection %s' % all_sections[parent]['id'])
            my_section.update({'masterSection': all_sections[parent]['id']})

        try:
            logging.debug(f'trying to add new section {name} to PHPIPAM')
            self._pi.create_entity(controller='sections', data=my_section)
        except Exception as exc:
            logging.critical("got exception: %s" % exc)
            return {'success': False, 'error': 'got exception %s' % exc}

        try:
            new_section = self._pi.get_entity(controller='sections', controller_path='%s/' % name)
            logging.info(f'added new section {name} to PHPIPAM')
            # save dict for later use
            all_sections[name] = {'id': new_section['id'],
                                'description': name
                                }
            return {'success': True,
                    'new_section': new_section['id'],
                    'log': 'section %s added to phpipam' % name}
        except Exception as exc:
            logging.critical("oh strange things happened! got exception: %s after adding section to PHPIPAM" % exc)
            return {'success': False, 'error': 'got exception %s' % exc}

    def add_subnet_to_phpipam(self, prefix, section, description, update=False):
        if not self._all_subnets:
            logging.debug("getting subnets")
            all_subnets = self.get_prefixe_from_phpipam("0.0.0.0/0")
        if not self.sections_by_name:
            logging.debug("getting sections")
            sections_by_id, sections_by_name = self.get_sections_from_phpipam()

        net, mask = prefix.split("/")
        if section in sections_by_name:
            section_id = sections_by_name[section]['id']
            logging.debug(f'found existing section; using section_id {section_id}')
        else:
            logging.debug(f'section {section} not found in PHPIPAM sections; creating new one')
            response = self.add_section_to_phpipam(section, section, None, sections_by_name)
            if not response['success']:
                logging.error(f'could not add section {section} to PHPIPAM')
                return {'success': False, 'error': 'could not add section %s to PHPIPAM' % section}
            section_id = response['new_section']
            logging.debug(f'section_id of new subnet {prefix} is {section_id} (parent:{section})')

        my_subnet = {
            "subnet": net,
            "mask": mask,
            "sectionId": section_id,
            "description": description
        }
        
        try:
            entity = self._pi.get_entity(controller='subnets', controller_path="/cidr/%s" % prefix)
            id = entity[0]['id']
            logging.debug(f'subnet {prefix} (id: {id}) found in PHPIPAM')
            if update:
                new_data = {"sectionId": section_id,
                            "description": description
                           }
                response = self._pi.update_entity(controller='subnets', controller_path=id, data=new_data)
                return {'success': True,
                        'log': 'subnet %s updated in phpipam' % prefix}
            else:
                return {'success': True,
                        'log': 'subnet %s already in phpipam' % prefix}
        except PHPyPAMEntityNotFoundException:
            try:
                self._pi.create_entity(controller='subnets', data=my_subnet)
                logging.debug(f'subnet {prefix}/{description} added to PHPIPAM')
                return {'success': True,
                        'id': 0,
                        'log': 'subnet %s added to phpipam' % prefix}
            except Exception as exc:
                logging.debug("could not add %s to PHPIPAM; got exception %s; looking for supernets" % (prefix, exc))
                for subnet in all_subnets:
                    prefix_cidr = IPv4Network(prefix, strict=False)
                    supernet = IPv4Network(subnet, strict=False)
                    logging.debug(f'checking if {prefix_cidr} lies in {supernet} ')
                    if prefix_cidr.subnet_of(supernet):
                        logging.debug(f'found possible masterSubnet of {prefix}: {subnet}')
                        masterSubnetId = self.get_id_of_network(subnet)
                        logging.debug(f'masterSubnetId is {masterSubnetId}')
                        # for later use
                        my_subnet.update({'masterSubnetId': masterSubnetId})
                        try:
                            self._pi.create_entity(controller='subnets', data=my_subnet)
                            logging.debug(f'subnet {prefix}/{description} added to PHPIPAM')
                            return {'success': True,
                                    'id': 1,
                                    'log': 'subnet %s added to phpipam' % prefix}
                        except Exception as exc:
                            logging.critical(f'could not add {prefix} to PHPIPAM; got exception {exc}; giving up')
                            return {'success': False, 'error': 'got exception %s' % exc}
                return {'success': False, 'error': 'could not add subnet %s; no supernet found but needed' % prefix}

    def get_id_of_network(self, prefix):
        logging.debug(f'looking for network {prefix}')
        try:
            network = self._pi.get_entity(controller='subnets', controller_path='/cidr/%s/' % prefix)
            if len(network) > 1:
                nn = len(network)
                logging.info(f'found multiple ({nn}) master subnets for {prefix}')
            network_id = network[0]['id']
            logging.debug(f'found network; id {network_id}')
            return network_id
        except PHPyPAMEntityNotFoundException as exc:
            return None

