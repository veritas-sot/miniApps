import phpypam
from loguru import logger
from phpypam.core.exceptions import PHPyPAMEntityNotFoundException, PHPyPAMException
from ipaddress import IPv4Network


class Phpipam(object):

    def __init__(self, url, app_id, username, password, ssl_verify):
        self._all_subnets = None
        self._sections_by_name = {}
        self._sections_by_id = {}
        self._folders_by_name = {}
        self._folders_by_id = {}
        self._folders_by_sectionid = {}
        self._locations_by_name = {}
        self._locations_by_id = {}
        self._customers_by_name = {}
        self._customers_by_id = {}
        self._pi = phpypam.api(url=url,
                               app_id=app_id,
                               username=username,
                               password=password,
                               ssl_verify=ssl_verify)
        self.load_data()

    def load_data(self):
        """get all PHPIPAM data that is needed later"""
        logger.debug('loading sections, subnets, folders and locations')
        self._all_subnets = self.get_prefixe("0.0.0.0/0")
        self._sections_by_id, self._sections_by_name = self.get_sections()
        self.get_folders()
        self.get_locations()

    def get_sections(self):
        sections_by_name = {}
        sections_by_id = {}

        # get all sections
        all_sections = self._pi.get_entity(controller='sections', controller_path='/')
        if all_sections is not None:
            for section in all_sections:
                section_name = section['name']
                logger.debug(f'got section {section_name} from PHPIPAM')
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

    def get_section(self, name):
        try:
            return self._pi.get_entity(controller=f'sections/{name}', controller_path='/')
        except Exception:
            return None

    def get_prefixe(self, prefix):
        subnets = {}
        if prefix == "0.0.0.0/0":
            cp = "/"
        else:
            cp = "/search/%s" % prefix
        try:
            all_subnets = self._pi.get_entity(controller='subnets', controller_path='%s' % cp)
            logger.debug("found subnets; parsing")
            for subnet in all_subnets:
                cidr = "%s/%s" % (subnet['subnet'], subnet['mask'])
                #logger.debug(f'prefix {cidr} is in PHPIPAM ({subnet.get("sectionId")})')
                subnets[cidr] = {'subnet': subnet['subnet'],
                                 'id': subnet['id'],
                                 'mask': subnet['mask'],
                                 'description': subnet['description'],
                                 'section_id': subnet['sectionId'],
                                 'master_subnet_id': subnet['masterSubnetId']}
        except (PHPyPAMEntityNotFoundException, PHPyPAMException):
            logger.info(f'no subnets for prefix {prefix} found; looking into details now')
            supernet = IPv4Network(prefix, strict=False)
            try:
                all_subnets = self._pi.get_entity(controller='subnets', controller_path='/')
                for subnet in all_subnets:
                    cidr = "%s/%s" % (subnet['subnet'], subnet['mask'])
                    net = IPv4Network(cidr, strict=False)
                    if net.subnet_of(supernet):
                        logger.debug(f'adding  {cidr} to subnets')
                        subnets[cidr] = {'subnet': subnet['subnet'],
                                         'id': subnet['id'],
                                         'mask': subnet['mask'],
                                         'description': subnet['description'],
                                         'section_id': subnet['sectionId'],
                                         'master_subnet_id': subnet['masterSubnetId']}
            except (PHPyPAMEntityNotFoundException, PHPyPAMException):
                logger.info("no subnets found for %s" % prefix)
        return subnets

    def get_folders(self):
        folders_by_name = {}
        folders_by_id = {}
        folders_by_sectionid = {}
    
        # get all sections
        try:
            all_folders = self._pi.get_entity(controller='folders', controller_path='/')
        except Exception:
            return {}, {}, {}
        if all_folders is not None:
            for folder in all_folders:
                folder_name = folder['description']
                logger.debug(f'got folder {folder_name} from PHPIPAM')
                folders_by_name[folder_name] = {'id': folder['id'],
                                                'sectionId': folder['sectionId'],
                                                'name': folder_name,
                                                'description': folder['description'],
                                                'masterSubnetId': folder['masterSubnetId']
                                               }
                folders_by_id[folder['id']] = {'id': folder['id'],
                                               'sectionId': folder['sectionId'],
                                               'name': folder_name,
                                               'description': folder['description'],
                                               'masterSubnetId': folder['masterSubnetId']
                                              }
                folders_by_sectionid[folder['sectionId']] = {}
                folders_by_sectionid[folder['sectionId']][folder_name] = {
                                                'id': folder['id'],
                                                'sectionId': folder['sectionId'],
                                                'name': folder_name,
                                                'description': folder['description'],
                                                'masterSubnetId': folder['masterSubnetId']
                                                }                                 
        self._folders_by_name = folders_by_name
        self._folders_by_id = folders_by_id
        self._folders_by_sectionid = folders_by_sectionid
        return folders_by_id, folders_by_name, folders_by_sectionid
     
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
        logger.debug(f'looking for network {prefix}')
        try:
            network = self._pi.get_entity(controller='subnets', controller_path='/cidr/%s/' % prefix)
            if len(network) > 1:
                nn = len(network)
                logger.info(f'found multiple ({nn}) master subnets for {prefix}')
            network_id = network[0]['id']
            logger.debug(f'found network; id {network_id}')
            return network_id
        except PHPyPAMEntityNotFoundException:
            return None

    def add_section(self, name, description, parent, permissions):
        my_section = {
            'name': name,
            'description': description,
            'permissions': permissions
        }

        if parent in self._sections_by_name:
            logger.debug('found parent in sections; using masterSection %s' % self._sections_by_name[parent]['id'])
            my_section.update({'masterSection': self._sections_by_name[parent]['id']})

        try:
            logger.debug(f'trying to add new section {name} to PHPIPAM')
            self._pi.create_entity(controller='sections', data=my_section)
        except Exception as exc:
            logger.critical("got exception: %s" % exc)
            return False

    def add_folder(self, name, section):
        section_id = self.get_section(section).get('id')
        folders_by_id, folders_by_name, folders_by_sectionid = self.get_folders()
        folder = folders_by_sectionid.get(section_id).get(name)

        if folder:
            logger.debug(f'folder {name} already exists in {section}')
            return True

        logger.debug(f'adding folder {name} in section {section}')
        my_folder = {
            'description': name,
            'sectionId': section_id,
            'isFolder': 1
        }

        try:
            self._pi.create_entity(controller='subnets', data=my_folder)
            return True
        except Exception as exc:
            logger.error(f'could not create foler {name} in {section}; got exception {exc}')
            return False

    def add_subnet(self, prefix, section, folder, subnet_config, description, update=False):
        # reload all data
        self.load_data()

        net, mask = prefix.split("/")
        if section in self._sections_by_name:
            section_id = self._sections_by_name[section]['id']
            logger.debug(f'found existing section; using section_id {section_id}')
        else:
            logger.error(f'section {section} not found in PHPIPAM')
            return False

        my_subnet = {
            "subnet": net,
            "mask": mask,
            "sectionId": section_id,
            "description": description,
        }

        if folder:
            folder_id = self._folders_by_sectionid.get(section_id,{}).get(folder,{}).get('id')
            if folder_id:
                my_subnet.update({'masterSubnetId': folder_id})

        # add or overwrite subnet config
        my_subnet.update(subnet_config)

        # # check if a location is configured
        if 'location' in subnet_config:
            location_name = subnet_config['location']
            location_id = self._locations_by_name.get(location_name)['id']
            logger.debug(f'location {location_name} is ID {location_id}')
            my_subnet['location'] = location_id

        try:
            entity = self._pi.get_entity(controller='subnets', controller_path=f'/cidr/{prefix}')
            id = entity[0]['id']
            logger.debug(f'subnet {prefix} (id: {id}) found in PHPIPAM')
            if update:
                logger.info(f'updating prefix {prefix} in PHPIPAM')
                # subnet and mask cannnot be 'updated'
                del my_subnet['subnet']
                del my_subnet['mask']
                self._pi.update_entity(controller='subnets', controller_path=id, data=my_subnet)
                return True
        except PHPyPAMEntityNotFoundException:
            try:
                self._pi.create_entity(controller='subnets', data=my_subnet)
                logger.info(f'subnet {prefix}/{description} added to PHPIPAM')
                return True
            except Exception as exc:
                logger.debug(f'could not add {prefix} to PHPIPAM; got exception {type(exc).__name__}; looking for supernets')
                # todo: more than one subnet can match. We have to use the longest matching prefix
                for subnet in self._all_subnets:
                    prefix_cidr = IPv4Network(prefix, strict=False)
                    supernet = IPv4Network(subnet, strict=False)
                    #logger.debug(f'checking if {prefix_cidr} lies in {supernet} ')
                    if prefix_cidr.subnet_of(supernet):
                        logger.debug(f'found possible masterSubnet of {prefix}: {subnet}')
                        masterSubnetId = self.get_id_of_network(subnet)
                        logger.debug(f'masterSubnetId is {masterSubnetId}')
                        # for later use
                        my_subnet.update({'masterSubnetId': masterSubnetId})
                        try:
                            self._pi.create_entity(controller='subnets', data=my_subnet)
                            logger.debug(f'subnet {prefix}/{description} added to PHPIPAM')
                            return True
                        except Exception as exc:
                            pass
                            # logger.critical(f'could not add {prefix} to PHPIPAM; got exception {exc}; giving up')
                logger.error(f'could not add subnet {prefix}; no supernet found but needed')
                return False

    def remove_subnet(self, prefix, id=None):
        """delete subnet in phpipam"""
        if id:
            self._remove_entity('subnets', id)
            return True
        else:
            try:
                subnet = self._get_entity(controller='subnets',
                                          controller_path=f'/cidr/{prefix}')
                self._remove_entity('subnets', subnet[0]['id'])
                return True  
            except PHPyPAMEntityNotFoundException:
                logger.error(f'subnet {prefix} not found')
                return False

    def add_address(self, address, update=False):
        """add address to subnet"""
        addr = address.get('address')
        prefix = address.get('parent',{}).get('prefix')
        primary = address.get('primary_ip4_for')
        if primary:
            hostname = primary[0].get('name')
        else:
            hostname = addr

        try:
            entity = self._pi.get_entity(controller='subnets', controller_path=f'/cidr/{prefix}')
            subnet_id = int(entity[0]['id'])
        except (PHPyPAMEntityNotFoundException, PHPyPAMException):
            logger.error(f'unknown prefix {prefix}')
            return False

        my_addr = {'ip': addr.split('/')[0],
                   'subnetId': subnet_id,
                   'description': address.get('description',''),
                   'hostname': hostname
                  }

        # check if address is already there
        try:
            entity = self._pi.get_entity(controller='addresses', controller_path=f'/search/{addr}')
            id = entity[0]['id']
            logger.debug(f'address {addr} (id: {id}) found in PHPIPAM')
            if update and len(entity) > 0:
                # the IP address and the subnet cannot be changed
                del my_addr['ip']
                del my_addr['subnetId']
                self._pi.update_entity(controller='addresses', controller_path=id, data=my_addr)
                return True
        except (PHPyPAMEntityNotFoundException, PHPyPAMException):
            logger.debug(f'address {addr} not found')

        # new address; add it to phpipam
        try:
            self._pi.create_entity(controller='addresses', data=my_addr)
            description = address.get('description','')
            logger.info(f'addresss {addr}/{description} added to subnet {prefix}')
            return True
        except Exception as exc:
            logger.error(f'could not add address {addr} to phpipam; got exceptiom {exc}')
            return False

    def add_location(self, location):
        return self._add_entity('tools/locations', location)
    
    def _get_entity(self, controller, controller_path=None, params=None):
        try:
            logger.debug(f'trying to get {controller}/{controller_path}/{params}')
            return self._pi.get_entity(controller=controller, 
                                        controller_path=controller_path,
                                        params=params)
        except Exception as exc:
            logger.critical("got exception: %s" % exc)
            return False

    def _add_entity(self, controller, data):
        try:
            logger.debug(f'trying to add {controller} to PHPIPAM')
            return self._pi.create_entity(controller=controller, data=data)
        except Exception as exc:
            logger.critical("got exception: %s" % exc)
            return False

    def _remove_entity(self, controller, id):
        try:
            logger.debug(f'trying to remove {controller} in PHPIPAM')
            return self._pi.delete_entity(controller=controller, controller_path=id)
        except Exception as exc:
            logger.critical("got exception: %s" % exc)
            return False

