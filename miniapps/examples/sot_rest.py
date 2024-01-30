#
# examples how to call sot.rest
#


sot = sot.Sot(token="your_token", url="_your_nautobot_url")
nb = sot.rest(url=kobold_config['sot']['nautobot'], token=kobold_config['sot']['token'])
nb.session()
response = nb.patch(url=f"api/{endpoint}/", json=data)
if response.status_code != 200:
    logging.error(f'could not update data; got error {response.content}')
else:
    logging.info(f'data updated')