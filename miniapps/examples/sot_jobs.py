#
# examples how to call sot.jobs
#


# init sot
sot = sot.Sot(token="your_token", url="_your_nautobot_url")

# how to call init_nornir to get the nornir object
nr = sot.job.on('name=lab-01.local') \
            .set(username='lab', password='lab', result='result', parse=False) \
            .add_data({'test': 'value', 'sot': ['cf_net']}) \
            .add_to_group(['cf_net']) \
            .add_group(groups) \
            .init_nornir()

# or simple
nr = sot.job.on('name=lab-01.local') \
            .set(username='lab', password='lab', result='result', parse=False) \
            .add_data({'test': 'value', 'sot': ['cf_net']}) \
            .get_facts

