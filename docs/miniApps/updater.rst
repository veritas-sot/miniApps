#######
Updater
#######

.. contents::

Brief overview
**************
The updater miniApp helps you to do mass updates of your devices.

Let it run
**********

.. code-block:: shell

    usage: updater.py [-h] [--config CONFIG] [--devices DEVICES] [--addresses ADDRESSES] 
                      [--loglevel LOGLEVEL] [--loghandler LOGHANDLER] [--uuid UUID]
                      [--bulk-update BULK_UPDATE] [--update UPDATE] [--template TEMPLATE] 
                      [--force] [--dry-run] [--add-missing-data]

    options:
    -h, --help            show this help message and exit
    --config CONFIG       updater config file
    --devices DEVICES     query to get list of devices
    --addresses ADDRESSES
                            query to get list of IP addresses
    --loglevel LOGLEVEL   used loglevel
    --loghandler LOGHANDLER
                            used log handler
    --uuid UUID           database logger uuid
    --bulk-update BULK_UPDATE
                            use file (csv, xlsx) to update data
    --update UPDATE       use yaml config to update data
    --template TEMPLATE   template to use to update value
    --force               force update even if checksum is equal
    --dry-run             print updates only
    --add-missing-data    add missing data if possible (eg. IP-address)

Bulk updates using CSV or XLSX files
************************************
To update dozens of devices, it is often easier to first export all the data to an Excel 
sheet, modify it and then import the changes back into the system.
The export of the data can be done using the miniApp kobold. The data is imported using 
the updater.

.. code-block:: shell

    ./updater.py --bulk-update modified_devices.xlsx

Use can use --force to update ALL rows of the sheet. By default, the updater tries to find 
out which devices need to be updated and only updates these.

.. tip::

    Exporting the checksum is very useful. The updater will check this hash to detect changes.

Updates using YML-configs
*************************
A configuration consists of a soure (how to get a value) and a destination (what to update). 
More precisely, so-called named_groups are defined at the source, which can then be used 
when updating the destination.

The '--device' parameter is used to specify which devices are to be processed and, if necessary, updated. 

The following example should illustrate this.

.. code-block:: yaml

        ---
        update:
          source:
            named_groups:
              hostname: ^(?P<alpha>(a|b|c))(?P<digits>\d+)\.
              device_type.model: ^(?P<model>(\w+))
          destination:
            location.name: __alpha____digits__
            location.location_type.name: branch

If a device begins with the character a, b or c and is followed by one or more digits, the letter is saved 
as "alpha" and the number as "digits". The example above updates the location name and location type of 
devices that meet these criteria. The new location name is set to "__alpha____digits__". Example: If the 
name of a device is a101.local, the location name is updated to a101 and the location type is set to branch.

More examples
*************

Change the hostname to uppercase
================================
To change the name of all devices from lower case to upper case, the following example can be used.

.. code-block:: yaml

    ---
    update:
      source:
        named_groups:
        hostname: ^(?P<name>(.*))
      destination:
        name: "__name@upper__"

Fill the hostname with zeros
============================
This example can be used to fill the device name with zeros. Use zfill(5) to fill the name with upto 5 zeros.

.. code-block:: yaml

    ---
    update:
      source:
        named_groups:
        hostname: ^(?P<host>(.*?))\.(?P<domain>(.*))
      destination:
        location.name: "__host@zfill(5)__.__domain__"
        location.location_type.name: ast

More settings
=============

The following parameter are supported:

    =========   ====== 
    Parameter   Output
    =========   ======
    @upper      change a phrase or string to UPPER case
    @lower      change a phrase or string to lower case
    @title      change a phrase tor string o a title case (first word upper case)
    @capwords   change a phrase or string to capwords
    @camel      change a phrase or string to camel case
    @zfill      fill a string with zeros
    =========   ======