#
# examples how to call sot.get
#


# init sot
sot = sot.Sot(token="your_token", url="_your_nautobot_url")
parameter = {'name': ''}
response = sot.get.query(values=['hostname', 'primary_ip4','site','custom_fields'],
                         parameter=parameter)