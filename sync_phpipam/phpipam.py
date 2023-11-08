import json
import phpypam
import logging
from pynautobot import api
from phpypam.core.exceptions import PHPyPAMEntityNotFoundException, PHPyPAMException
from ipaddress import IPv4Network

class Phpipam(object):

    def __init__(self, url, app_id, username, password, ssl_verify):
        self._all_subnets = None
        self._sections_by_name = None
        self._sections_by_id = None
        self._locations_by_name = {}
        self._locations_by_id = {}
        self._customers_by_name = {}
        self._customers_by_id = {}
        self._pi = phpypam.api(url=url,
                               app_id=app_id,
                               username=username,
                               password=password,
                               ssl_verify=ssl_verify)
        self.load_sections_and_subnets()

    def load_sections_and_subnets(self):
        """get sections and subnets from PHPIPAM"""
        logging.debug('loading sections and subnets')
        self._all_subnets = self.get_prefixe("0.0.0.0/0")
        self._sections_by_id, self._sections_by_name = self.get_sections()

    def get_sections(self):
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

    def get_prefixe(self, prefix):
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
                # logging.debug(f'prefix {cidr} is in PHPIPAM ({subnet.get("sectionId")})')
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

    def get_locations(self):
        try:
            all_locations = self._pi.get_entity(controller='tools/locations', controller_path='/')
        except PHPyPAMEntityNotFoundException:
            return {},{}

        if all_locations is not None:
            for location in all_locations:
                location_name = location['name']
                self._locations_by_name[location_name] = {'id': location['id'],
                                                          'name': location_name,
                                                          'description': location['description'],
                                                         }
                self._locations_by_id[location['id']] = {'id': location['id'],
                                                         'name': location_name,
                                                         'description': location['description'],
                                                        }  
            return self._locations_by_id, self._locations_by_name

    def get_customers(self):
        try:
            all_customers = self._pi.get_entity(controller='tools/customers', controller_path='/')
        except PHPyPAMEntityNotFoundException:
            return {},{}

        if all_customers is not None:
            for customer in all_customers:
                customer_name = customer['title']
                self._customers_by_name[customer_name] = {'id': customer['id'],
                                                          'title': customer_name
                                                         }
                self._customers_by_id[customer['id']] = {'id': customer['id'],
                                                          'name': customer_name
                                                        }  
            return self._customers_by_id, self._customers_by_name

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

    def add_section(self, name, description, parent, permissions):
        my_section = {
            'name': name,
            'description': description,
            'permissions': permissions
        }

        if parent in self._sections_by_name:
            logging.debug('found parent in sections; using masterSection %s' % self._sections_by_name[parent]['id'])
            my_section.update({'masterSection': self._sections_by_name[parent]['id']})

        try:
            logging.debug(f'trying to add new section {name} to PHPIPAM')
            self._pi.create_entity(controller='sections', data=my_section)
        except Exception as exc:
            logging.critical("got exception: %s" % exc)
            return False

    def add_subnet(self, prefix, section, subnet_config, description, update=False):
        # reload all data
        self.load_sections_and_subnets()
        self.get_locations()

        net, mask = prefix.split("/")
        if section in self._sections_by_name:
            section_id = self._sections_by_name[section]['id']
            logging.debug(f'found existing section; using section_id {section_id}')
        else:
            logging.error(f'section {section} not found in PHPIPAM')
            return False

        my_subnet = {
            "subnet": net,
            "mask": mask,
            "sectionId": section_id,
            "description": description
        }

        # add or overwrite subnet config
        my_subnet.update(subnet_config)

        # # check if a location is configured
        if 'location' in subnet_config:
            location_name = subnet_config['location']
            location_id = self._locations_by_name.get(location_name)['id']
            logging.debug(f'location {location_name} is ID {location_id}')
            my_subnet['location'] = location_id

        try:
            entity = self._pi.get_entity(controller='subnets', controller_path=f'/cidr/{prefix}')
            id = entity[0]['id']
            logging.debug(f'subnet {prefix} (id: {id}) found in PHPIPAM')
            if update:
                logging.info(f'updating prefix {prefix} in PHPIPAM')
                # subnet and mask cannnot be 'updated'
                del my_subnet['subnet']
                del my_subnet['mask']
                response = self._pi.update_entity(controller='subnets', controller_path=id, data=my_subnet)
                return True
        except PHPyPAMEntityNotFoundException:
            try:
                self._pi.create_entity(controller='subnets', data=my_subnet)
                logging.info(f'subnet {prefix}/{description} added to PHPIPAM')
                return True
            except Exception as exc:
                logging.debug(f'could not add {prefix} to PHPIPAM; got exception {type(exc).__name__}; looking for supernets')
                # todo: more than one subnet can match. We have to use the longest matching prefix
                for subnet in self._all_subnets:
                    prefix_cidr = IPv4Network(prefix, strict=False)
                    supernet = IPv4Network(subnet, strict=False)
                    #logging.debug(f'checking if {prefix_cidr} lies in {supernet} ')
                    if prefix_cidr.subnet_of(supernet):
                        logging.debug(f'found possible masterSubnet of {prefix}: {subnet}')
                        masterSubnetId = self.get_id_of_network(subnet)
                        logging.debug(f'masterSubnetId is {masterSubnetId}')
                        # for later use
                        my_subnet.update({'masterSubnetId': masterSubnetId})
                        try:
                            self._pi.create_entity(controller='subnets', data=my_subnet)
                            logging.debug(f'subnet {prefix}/{description} added to PHPIPAM')
                            return True
                        except Exception as exc:
                            pass
                            # logging.critical(f'could not add {prefix} to PHPIPAM; got exception {exc}; giving up')
                logging.error(f'could not add subnet {prefix}; no supernet found but needed')
                return False

    def add_location(self, location):
        return self._add_entity('tools/locations', location)
    
    def _add_entity(self, controller, data):
        try:
            logging.debug(f'trying to add {controller} to PHPIPAM')
            return self._pi.create_entity(controller=controller, data=data)
        except Exception as exc:
            logging.critical("got exception: %s" % exc)
            return False

