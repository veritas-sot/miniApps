###############
veritas journal
###############

.. contents::

Brief overview
**************

One task of a modern network management system is to process numerous recurring jobs. 
For example, regular backups of device configurations must be created or configurations checked.

With all these many tasks, the network engineer quickly loses the overview. Which jobs have been 
successfully completed, and which have had problems.

The legacy system provided an overview of the jobs. With the replacement of the old system and the 
introduction of a new open source-based system, the possibility of obtaining an overview of the jobs 
also had to be created.

The 'veritas' journal exists to keep track of everything. 

Don't lose the overview
***********************

You know the situation: A device breaks down and needs to be replaced. The last backup of the configuration 
is needed for this. When restoring the configuration, it is recognized that the backup has not been running 
for some time and the configuration does not correspond to the current status.  It's a classic....

If jobs are running in the background, they must always be checked. Jobs write logs to show the progress. 
However, if several jobs are running and they access hundreds of devices, it is easy to lose track.

This is why the 'veritas' journal exists. All miniApps can write messages to the journal. Once all activities have 
been completed, the 'Journal' is closed and a report is written to the network administrators. The most important 
points are summarized in this report: Which jobs were completed successfully, where there were which problems.

How to store logs
*****************

The journal, all activities and their logs as well as messages and a simple key/value uses a postgresql database. 
The table structure is as follows.

The database layout
"""""""""""""""""""

For each journal an entry in the journal database is added. Each journal gets its unique identifier (uuid) 

.. code-block:: python

    CREATE TABLE public.journals
    (
        uuid uuid NOT NULL DEFAULT gen_random_uuid(),
        opened timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
        closed timestamp with time zone,
        status status DEFAULT 'active'::status,
        PRIMARY KEY (uuid)
    );

'activities' are jobs that mostly run in the background. In principle, such a job can also be started by a user. 
In most cases, however, a network administrator will not create a 'journal entry' and will instead run the job 
'normally' in a shell.

.. code-block:: python

    CREATE TABLE IF NOT EXISTS public.activities
    (
        id serial,
        uuid uuid NOT NULL DEFAULT gen_random_uuid(),
        journal_uuid uuid NOT NULL,
        app character varying(100),
        activity character varying(200) NOT NULL,
        started timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        CONSTRAINT unique_uuid UNIQUE (uuid),
        CONSTRAINT jrnl_uuid FOREIGN KEY (journal_uuid)
            REFERENCES public.journals (uuid) MATCH SIMPLE
            ON UPDATE NO ACTION
            ON DELETE SET NULL
            NOT VALID
    );

Every app can generate logs. If a user wants the logs to be saved in the database, they specify a uuid when 
starting the app. This means that all logs (depending on the configured log level) are sent to the dispatcher 
and thus to the database.

.. code-block:: python

    CREATE TABLE IF NOT EXISTS public.logs
    (
        id serial NOT NULL,
        uuid uuid,
        app character varying(100) COLLATE pg_catalog."default",
        date timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
        levelno integer,
        levelname character varying(10) COLLATE pg_catalog."default",
        function character varying(1024) COLLATE pg_catalog."default",
        functionname character varying(1024) COLLATE pg_catalog."default",
        module character varying(100) COLLATE pg_catalog."default",
        processname character varying(100) COLLATE pg_catalog."default",
        threadname character varying(100) COLLATE pg_catalog."default",
        lineno integer,
        message character varying(1024) COLLATE pg_catalog."default",
        filename character varying(1024) COLLATE pg_catalog."default",
        pathname character varying(1024) COLLATE pg_catalog."default",
        exception character varying(1024) COLLATE pg_catalog."default",
        extra character varying(1024) COLLATE pg_catalog."default",
        CONSTRAINT log_pkey PRIMARY KEY (id),
        CONSTRAINT activity_uuid FOREIGN KEY (uuid)
            REFERENCES public.activities (uuid) MATCH SIMPLE
            ON UPDATE NO ACTION
            ON DELETE SET NULL
            NOT VALID
    );

The results of the executed jobs must be evaluated in some form. It would be possible to do this 
by parsing the logs. However, this is very cumbersome and error-prone. For this reason, an app can 
send so-called 'results' to the dispatcher. These 'reults' reflect the result of the job.

.. code-block:: python

    CREATE TABLE IF NOT EXISTS public.results
    (
        id serial NOT NULL,
        uuid uuid,
        app character varying(100) COLLATE pg_catalog."default",
        entity character varying(80) COLLATE pg_catalog."default",
        message character varying(1024) COLLATE pg_catalog."default",
        CONSTRAINT results_pkey PRIMARY KEY (id),
        CONSTRAINT activity_uuid FOREIGN KEY (uuid)
            REFERENCES public.activities (uuid) MATCH SIMPLE
            ON UPDATE NO ACTION
            ON DELETE SET NULL
            NOT VALID
    )

In order to give the user an overview of the process of an app, it can also write messages to the database.

.. code-block:: python

    CREATE TABLE IF NOT EXISTS public.messages
    (
        id serial,
        uuid uuid,
        app character varying(80),
        message text,
        PRIMARY KEY (id),
        CONSTRAINT msg_uuid FOREIGN KEY (uuid)
            REFERENCES public.journals (uuid) MATCH SIMPLE
            ON UPDATE NO ACTION
            ON DELETE SET NULL
            NOT VALID
    );

The activities of a 'journal' can be spread over several days. For example, the backup of a large network can be 
divided into smaller jobs. All these activities should be summarized in the evaluation. To achieve this, all 
activities that are to be summarized later use the same journal uuid. This uuid is stored in the 'store' and can 
be queried by any app.

.. code-block:: python

    CREATE TABLE IF NOT EXISTS public.store
    (
        app character varying(80) NULL,
        key character varying(1024) NOT NULL,
        value character varying(1024) NOT NULL,
        CONSTRAINT primary_key PRIMARY KEY (key, value, app)
    );


How to collect logs
*******************
Collecting logs is simple. The miniApp enables the messagebus which send the logs via rabbitmq to a dispatcher.
The dispatcher collects the logs and writes them to the database.

How to send logs
""""""""""""""""
There are two cases how to send logs to the dispacther. You can either enable the feature 'log_to_rabbitmq' in 
your config or you can set 'log_uuid_to' to rabbitmq. The first option enables sending all logs to the dispatcher 
whereas the second option enables the messagebus if a uuid was specified when starting the miniApp.

The default logging config is as follows:

.. code-block:: yaml

    general:
      logging:
          loglevel: info
          log_uuid_to: rabbitmq
          log_to_database: false
          log_to_rabbitmq: false
          log_to_zeromq: false
          rabbitmq:
            host: 127.0.0.1
            port: 5672

If you are developing your own miniApp you can send logs by calling 'veritas.logging.create_logger_environment' first and
then use the logger object to send logs.

.. code-block:: python

    # get loglevel, loglhandler and uuid from cmd argument
    parser = argparse.ArgumentParser()
    parser.add_argument('--loglevel', type=str, required=False, help="used loglevel")
    parser.add_argument('--loghandler', type=str, required=False, help="used log handler")
    parser.add_argument('--uuid', type=str, required=False, help="unique identifier")
    args = parser.parse_args()

    # create logger environment
    veritas.logging.create_logger_environment(
        config=local_config_file, 
        cfg_loglevel=args.loglevel,
        cfg_loghandler=args.loghandler,
        app='your_app_name',
        uuid=args.uuid)

You can send 'results' by binding the dict to your logger. In the example the dict 'result' is sent to the 
dispatcher and then written to the database. 

.. code-block:: python

    result = {'app': 'your_app_name',
              'details': {
                'entity': hostname,
                'message': 'something happened'}
             }
    logger.bind(result=result).journal(f'something happened on {hostname}')

How to receive logs
"""""""""""""""""""
The task of the 'dispatcher' is to receive the logs and write them to the database. A simple rabbitmq base 
dispatcher can be found in './dispatcher/dispatcher.py' precisely in the plugins subdirectory of the dispatcher file.

.. code-block:: python

    usage: dispatcher.py [-h] [--loglevel LOGLEVEL] [--loghandler LOGHANDLER] 
                         [--binding-keys [BINDING_KEYS ...]] [--stdout]

    options:
    -h, --help            show this help message and exit
    --loglevel LOGLEVEL   used loglevel
    --loghandler LOGHANDLER
                            used log handler
    --binding-keys [BINDING_KEYS ...]
                            which logs to dispatch
    --stdout              write to stdout instead to database

The parameter binding-keys is used to collect all (use '#') or only a part of the logs (eg. "#.journal"). Look at the rbbitmq 
documentation on how to configure binding keys.

.. tip::

    - The routing key must be a list of words, delimited by a period (.)
    - \* matches a word in a specific position of the routing key
    - \# indicates a match of zero or more words 

    An example:

    .. code-block:: python

        ./dispatcher.py --binding-keys "#.journal"

    collects all logs with the log level 'journal'.

How to visualize logs
*********************
Use the miniApp ./journal.py to habve a look at your journals

.. code-block:: shell

    usage: journal.py [-h] [--close CLOSE] [--report REPORT] [--list] [--loglevel LOGLEVEL] 
                      [--journal JOURNAL] [--logs LOGS] [--all] [--extra] [--cols COLS] [--show-logs]

    options:
    -h, --help           show this help message and exit
    --close CLOSE        close journal
    --report REPORT      report journal
    --list               list all open kournals
    --loglevel LOGLEVEL  used loglevel
    --journal JOURNAL    show details of journal
    --logs LOGS          show logs of journal
    --all                show full details
    --extra              show extra column (logs)
    --cols COLS          list of columns (logs)
    --show-logs          show logs (journal details)

To list all journals use '--list'

.. code-block:: shell

    >>> ./journal.py --list
                                        Active Journals
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
    ┃ journal_uuid                         ┃ opened                           ┃ closed ┃ status ┃
    ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
    │ d8564782-fd8d-44f4-ace8-8476f3e14e08 │ 2024-01-29 12:22:37.788850+00:00 │ None   │ active │
    └──────────────────────────────────────┴──────────────────────────────────┴────────┴────────┘

As you can see, there is one 'active' journal. To see what 'activities' the journal has performed use

.. code-block:: shell

    >>> ./journal.py --journal d8564782-fd8d-44f4-ace8-8476f3e14e08
                                                                      Activities
    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
    ┃ activity_uuid                        ┃ app             ┃ activity                              ┃ started                          ┃ journal_status ┃
    ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
    │ 1e22501b-af01-47fd-81c4-57f85bb40ed8 │ compare_configs │ comparing running and startup configs │ 2024-01-29 12:22:37.814429+00:00 │ active         │
    └──────────────────────────────────────┴─────────────────┴───────────────────────────────────────┴──────────────────────────────────┴────────────────┘

And to get all logs

.. code-block:: shell

    >>> ./journal.py --logs 1e22501b-af01-47fd-81c4-57f85bb40ed8
                                                            Logs
    ┏━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃ id   ┃ app             ┃ date                             ┃ levelname ┃ module          ┃ message                    ┃
    ┡━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
    │ 2535 │ compare_configs │ 2024-01-29 12:22:38.545853+00:00 │ journal   │ compare_configs │ no diff found on lab.local │
    └──────┴─────────────────┴──────────────────────────────────┴───────────┴─────────────────┴────────────────────────────┘

