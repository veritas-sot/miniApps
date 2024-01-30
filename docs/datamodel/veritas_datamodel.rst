#################
veritas Datamodel
#################

Veritas uses additional fields to define certain properties of the devices in 
nautobot. For example, veritas uses the 'Custom Field' 'snmp_credentials'. 
This field identifies the SNMP credentials that are required to query the device.

The table below lists all device based veritas properties.

.. list-table:: veritas Datamodel (dcim.devices)
   :widths: 25 25 40 40
   :header-rows: 1

   * - Name
     - Type
     - Description
     - miniApp
   * - net
     - custom_field
     - | Name of the network in which the 
       | device is running
     - sync_smokeping
   * - snmp_credentials
     - custom_field
     - | ID of the SNMP credential of the device
       | There must be a corresponding ID in 
       | your defaults/snmp_credentials.yaml
     - | set_snmp, 
       | sync_cmk
   * - link
     - custom_field
     - How is the device connected?
     - set_link
   * - latency
     - custom_field
     - The latency of this device
     - set_latency
   * - checkmk_folder
     - custom_field
     - In which folder should the device placed.
     - sync_cmk
   * - checkmk_htg
     - custom_field
     - Addition host tag groups of this device
     - sync_cmk
   * - scan_prefix
     - custom_field
     - True if the prefix should be scanned
     - job_scan_prefixes

It is up to you whether you also use these fields. If you do not, the associated 
miniApps are of course useless to you.

