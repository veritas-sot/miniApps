#
# examples how to call sot.select
#


# init sot
sot = sot.Sot(token="your_token", url="_your_nautobot_url")

devices = my_sot.select(['hostname']) \
                .using('nb.devices') \
                .normalize(True) \
                .where('site=default-site or site=mysite')
print(devices)

devices = my_sot.select(['prefix','description','vlan', 'site']) \
                .using('nb.ipam') \
                .normalize(True) \
                .where('within_include=10.0.0.0/8')
print(devices)

all_prefixe = my_sot.select(['prefix','description','vlan', 'site']) \
                .using('nb.ipam') \
                .normalize(True) \
                .where()
print(all_prefixe)

device = my_sot.select('id,hostname') \
               .using('nb.devices') \
               .normalize(True) \
               .where('primary_ip4=192.168.0.1')
print(device)

vlans = my_sot.select('vlans') \
                .using('nb.general') \
                .normalize(False) \
                .where('site=mysite')
print(vlans)

sites = my_sot.select('sites') \
                .using('nb.general') \
                .normalize(False) \
                .where('name=mysite')
print(sites)

all_sites = my_sot.select('sites') \
                .using('nb.general') \
                .normalize(False) \
                .where()
print(all_sites)
