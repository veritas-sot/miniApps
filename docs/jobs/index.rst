############
veritas Jobs
############

Using the veritas-sot library it is easy do develop your own jobs.

Currently three jobs are part of the veritas-toolkit

**************
Backup configs
**************

The following code illustrates how to do a backup easily. We use two decorators to 

- enable the journal
- execute the job on a specific day

.. code-block:: python

    @journal.activity(journal=args.id, 
                      app='backup_configs', 
                      description='backup device configs')

This decorator ensures that either a new journal is created if the ID does not yet exist, 
or a new activity is added to the known journal.

.. code-block:: python

    @on(['monday'])

The following method is only execute on a monday.

The complete code looks like this.

.. code-block:: python

    #!/usr/bin/env python

    import sys
    import argparse

    # veritas
    from veritas.cron import on
    from veritas.tools import tools
    from veritas.journal import journal
    from veritas.logging import minimal_logger

    # set import path to our script_bakery
    sys.path.append('../script_bakery')
    # and now import the backup script
    import backup_configs as backup

    def main():

        parser = argparse.ArgumentParser()
        parser.add_argument('--id', type=str, default="backup_configs", required=False, help="the key to get the uuid")
        parser.add_argument('--profile', type=str, required=True, help="profile to get login credentials")
        parser.add_argument('--loglevel', type=str, required=False, default="INFO", help="used loglevel")

        args = parser.parse_args()

        minimal_logger(args.loglevel)

        @journal.activity(journal=args.id, 
                          app='backup_configs', 
                          description='backup device configs')
        @on(['monday'])
        def do_backup(*args, **kwargs):
            properties = tools.convert_arguments_to_properties(args, kwargs)
            args = properties.get('args')
            backup.main(['--profile', args.profile, 
                         '--loglevel', args.loglevel,
                         '--devices', 'name=lab.local',
                         '--uuid', properties['uuid']])

        do_backup(args=args)

    if __name__ == "__main__":
        main()

***************
Compare configs
***************


************
Sync CheckMK
************