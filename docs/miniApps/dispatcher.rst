##########
Dispatcher
##########

.. contents::

Brief overview
**************
This miniApp retrieves logs either from rabbit or from zeromq and writes it to the database or prints it to the console.

How to use it
*************
The dispatcher uses a plugin architeture to retrieve logs from different sources and to write logs to different destinations. 
The plugins are loaded from the configuration file. The configuration file is a yaml file that looks like this:

.. code-block:: yaml

        ---
        general:
          # Some lines on how to configure logging have been omitted
          dispatcher:
            plugin_dir: plugins
            plugin: dispatcher_rabbitmq
          database:
            # these values almost always match the 'logging' values.
            host: 127.0.0.1
            database: journal
            user: postgres
            password: postgres
            port: 5432
        zeromq:
          protocol: tcp
          host: 127.0.0.1
          port: 12345
          filter: journal
        rabbitmq:
          host: 127.0.0.1
          port: 5672

The mandatory fields to use plugins are **plugin_dir** and **plugin**. The plugin_dir is the directory where 
the plugins are located. The plugin is the name of the plugin that will be used to retrieve logs. 
The plugin is a python file that contains a class that inherits from the abstract_dispatcher class. 

To use a python class as a plugin, you must use a decorator to register the method that initializes the plugin.

.. code-block:: python

    @plugin.register('dispatcher')
    def dispatch(config):
        """dispatch logs to database"""

        logger.info('dispatching logs to database or stdout')
        dispatcher = Dispatcher(config)
        return dispatcher

Two examples of plugins are provided: dispatcher_rabbitmq and dispatcher_zeromq. The dispatcher_rabbitmq plugin is a 
plugin that retrieves logs from rabbitmq. It writes the logs either to the database or to the console.
It can be used as follows:

.. code-block:: shell

        usage: dispatcher.py [-h] [--loglevel LOGLEVEL] [--loghandler LOGHANDLER] [--binding-keys [BINDING_KEYS ...]] [--stdout]

        options:
        -h, --help            show this help message and exit
        --loglevel LOGLEVEL   used loglevel
        --loghandler LOGHANDLER
                                used log handler
        --binding-keys [BINDING_KEYS ...]
                                which logs to dispatch
        --stdout              write to stdout instead to database

RabbitMQ binding keys
*********************
Binding keys are used to filter logs. The default binding key is '#' and means that all logs are retrieved.

.. note::

    The binding key may contain an asterisk (“*”) to match a word in a specific position. 
    For example, the binding key “app.debug” matches the log “app.debug” but not “app.b.debug”. 
    The symbol (“#”) indicates a match of zero or more words e.g., a routing pattern of 
    "app.debug.#" matches any routing keys beginning with "app.debug". The binding key “#” matches all logs.

The Database structure
**********************
The dispatcher uses two database tables: logs and results. The logs table is used to store logs and the 
results table is used to store results. The tables have the following structure:

.. code-block:: sql

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
    )

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

Both tables have a foreign key to the activities table. The activities table is used to store the activity id.
The activities table has the following structure:

.. code-block:: sql

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
    )

This table has a foreign key to the journals table. The journals table is used to store the journal id.

The journals table has the following structure:

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS public.journals
    (
      uuid uuid NOT NULL DEFAULT gen_random_uuid(),
      opened timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
      closed timestamp with time zone,
      status status DEFAULT 'active'::status,
      PRIMARY KEY (uuid)
    )

.. tip::

    To install the database you can use the miniApp **create_database_tables.py** that can be found in the installation directory.

