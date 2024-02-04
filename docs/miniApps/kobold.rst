######
Kobold
######

.. contents::

Brief overview
**************
Kobold is a miniApp to export, update and transform device properties. 

Let it run
**********

.. code-block:: shell

      usage: kobold.py [-h] [--loglevel LOGLEVEL] [--loghandler LOGHANDLER] 
                       [--uuid UUID] [--config CONFIG] {update,export,transform} ...

      positional arguments:
        {update,export,transform}
          update              update devices
          export              export data of devices
          transform           transform properties of devices

      options:
        -h, --help            show this help message and exit
        --loglevel LOGLEVEL   used loglevel
        --loghandler LOGHANDLER
                              used log handler
        --uuid UUID           database logger uuid
        --config CONFIG       updater config file


General arguments
*****************

You can set the loglevel, loghandler and the UUID for all the commands. The syntax is:

.. code-block:: shell

    >>> ./kobold --loglevel debug {update,export,transform} ....

You must therefore write these three parameters at **the beginning** of the command.

Exporter
********
To export device properties, configs, facts or the HLDM use the exporter. 

.. code-block:: shell

      usage: kobold.py export [-h] --playbook PLAYBOOK 
                               --job JOB (--profile PROFILE | --username USERNAME | --password PASSWORD)

      options:
        -h, --help           show this help message and exit
        --playbook PLAYBOOK  playbook config to use
        --job JOB            job to run
        --profile PROFILE    profile to get login credentials
        --username USERNAME  login username
        --password PASSWORD  login password

To use the exporter you have to write a playbook. A playbook looks like this:

.. code-block:: yaml

      ---
      jobs:
        - job: export_properties
          description: export properties
          devices:
            sql:
              # the values of the select statement must correspond must include the columns you
              # want to export
              select: id, name, primary_ip4
              from: nb.devices
              where: name__ic=local
          tasks:
            - export: 
              - content: properties
                header: True
                columns: id, name, primary_ip4.address, primary_ip4.interfaces.name, checksum
                format: excel
                filename: ./export/properties.xlsx

The parameter content specifies what to do. It is either properties, config, facts or hldm.

Export device properties
========================

Using the playbook above, the miniApp exports the **device properties**

  - id
  - name
  - primary_ip4.address (the primary IP Address)
  - primary_ip4.interfaces.name (the name of the primary interface)

and writes the data to a xlsx file named './export/properties.xlsx'. You must specify a job to run it.
The result looks like this:

.. code-block:: shell

    >>> ./kobold.py export --profile default --playbook playbooks/export.yaml --job export_properties

.. image:: ./kobold_export.png
  :width: 700
  :alt: Kobold export

You can then modify the data and reimport it using the kobold updater.

Export the HLDM
===============
To export the HLDM of devices use this playbook:

.. code-block:: yaml

    - job: export_hldm
      description: export HLDM
      devices:
        sql:
          select: name
          from: nb.devices
          where: name=lab.local
      tasks:
        - export:
          - content: hldm
            directory: hldm/__location.name__
            filename: __name__.json

And then use this command:

.. code-block:: shell

    >>> ./kobold.py export --profile default --playbook playbooks/export.yaml --job export_hldm
    2024-02-04 16:40:20 | INFO | unset | starting job export_hldm / export HLDM
    2024-02-04 16:40:20 | INFO | unset | exporting [{'content': 'hldm', 'directory': 'hldm/__cf_net__/__location.name__', 'filename': '__name__.json'}]


Updater
*******
With the help of the updater you can:

  - import data that was exported (and maybe modified)
  - update device properties
  - transform device properties (upper case device names etc.)

.. code-block:: shell

      usage: kobold.py update [-h] --filename FILENAME [--job JOB] [--where WHERE] 
                              [--force] [--dry-run] [--add-missing-data]

      options:
        -h, --help           show this help message and exit
        --filename FILENAME  name of file to update data
        --job JOB            job to run
        --where WHERE        overwrite where statement
        --force              force bulk updates even if checksum equals
        --dry-run            print updates only
        --add-missing-data   add missing data if possible (eg. IP-address)

Import csv and xlsx files
=========================
To re-import some device data that was exported and modified before, use this command:

.. code-block:: shell

    ./kobold.py update --filename export/properties.xlsx [--add-missing-data]
  
This updates the data. If you change the primary interface and the primary IP address and 
these are not yet in the IPAM, the --add-missing-data parameter must be added.

Update device properties or set tags
====================================
The miniApp directory contains several examples. In ./kobold/updates/ you find examples to:

  - set, add, or delete device tags
  - set, add, or delete interface tags
  - update device properties
  - update device properties using the IP-Address of the device (and not the name)
  - update interface properties

Let's have a look at one example:

.. code-block:: yaml

      ---
      update:
        - job: update_device_property
          description: Set device property
          source:
            select: name
            from: nb.devices
            where: name__ic=local
          tasks:
            - device_property:
                serial: my_new_serial
                status: {'name': 'Active'}
                custom_fields: {'net': 'my_net'}

Each job consists of a job identifier, a description (optional), a source and the tasks. 

.. tip::

  To get the list of devices use:

    .. code-block:: yaml

      devices:
          select: name, interfaces
          from: nb.devices
          where: name=lab-01.zz and interfaces_name=Loopback0
      
    where 
      - 'select' specifies what properties to get
      - 'from' the name of the 'nautobot module' and
      - 'where' a SQL-like statement what devices to get.

  Using --where as an argument overwrites the configured where statement! 

You can set device properties by using 'device_property' as task. Have a look at the next example to see 
how to set, add or delete a tag.

.. code-block:: yaml

    tasks:
      - delete_tag:
          scope: dcim.device
          tag: test
      - add_tag:
          scope: dcim.device
          tag: test2
      - set_tag:
          scope: dcim.device
          tag: test

To update an interface, look at this example:

.. code-block:: yaml

      ---
      update:
        - job: update_device_property
          description: Set device property
          source:
            select: name, interfaces
            from: nb.devices
            where: name__ic=local and interfaces_name=Loopback0
          tasks:
            - interface_property:
                status: {'name': 'Active'}

This sets the status of all interfaces to 'Active' whose device has the word local in its name.

Transformer
***********
To transform some device properties use the transform command.

.. code-block:: shell

      usage: kobold.py transform [-h] --filename FILENAME [--job JOB] [--where WHERE] 
                                 [--template TEMPLATE] [--dry-run]

      options:
        -h, --help           show this help message and exit
        --filename FILENAME  name of file to transform data
        --job JOB            job to run
        --where WHERE        overwrite where statement
        --template TEMPLATE  template to use to update value
        --dry-run            print updates only
        
If you do not specify a job, all jobs in the file will be executed. The directory
./kobold/transforms contains some examples. The structure of the configuration is 
similar to that of the update.

.. code-block:: yaml

    ---
    transform:
      - job: name_to_upper
        description: change hostname to upper case
        source:
          from: nb.devices
          where: name__ic=local
          named_groups:
            name: ^(?P<name>(.*))
        destination:
          name: "__name@upper__"

To transform a property you have to specify a 'source' and a 'destination'. 
On the one hand, the source specifies which devices are to be processed. On the other hand 
the source contains a regular expression, to be more precise a named group. This named group is 
used to transform the destination value. In the example above the named group catches the device name and 
saves this value in the variable 'name'. This variable and a modifier (eg. upper) is then used to 
transform the property.

Another example illustrates how to transform the location.

.. code-block:: yaml

      ---
      transform:
        - job: update_location
          description: Update Location to a001....
          source:
            from: nb.devices
            where: name__ic=local
            named_groups:
              hostname: ^(?P<alpha>(a|b|c))(?P<digits>\d+)\.
              device_type.model: ^(?P<model>(\w+))
          destination:
            location.name: __alpha____digits__
            location.location_type.name: branch
