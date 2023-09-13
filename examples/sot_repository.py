#
# examples how to call sot.repo
#


sot = sot.Sot(token="your_token", url="_your_nautobot_url")
name_of_repo = args.repo or onboarding_config['files']['defaults']['repo']
path_to_repo = args.path or onboarding_config['files']['defaults']['path']
filename = args.defaults or onboarding_config['files']['defaults']['filename']
logging.debug("reading %s from %s" % (filename, name_of_repo))
default_repo = sot.repository(repo=name_of_repo, path=path_to_repo)
if default_repo.has_changes():
    logging.warning(f'repo {name_of_repo} has changes')
defaults_str = default_repo.get(filename)
if defaults_str is None:
    logging.error("could not load defaults")
    raise Exception('could not load defaults')
