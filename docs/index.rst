Welcome to veritas toolkit's documentation!
===========================================

.. toctree::
   :hidden:
   :titlesonly:

   datamodel/veritas_datamodel.rst
   miniApps/index.rst
   jupyter_notebooks/index.rst
   journal/index.rst
   jobs/index.rst

`veritas <https://veritas-sot.readthedocs.io/en/latest/>`_ and its toolkit was originally developed to replace an 
existing commercial network management system as quickly as possible with an open source solution. Since 
network engineers are usually not (Python) developers, a library had to be developed to make their life with 
`nautobot <https://github.com/nautobot>`_ and the API as easy as possible.

The library consists of several parts. On the one hand, complex queries can be made relatively simply using a 
syntax based on 'SQL'. On the other hand, the library makes it very easy to add or update several hundred 
devices to nautobot.

veritas is in a very “early” stage and can only be described as experimental. However, the migration of our 
legacy system was successfully completed with this library and the associated toolkit.
In order to enable others to migrate their system, we have decided to publish the library and the toolkit.

veritas and its toolkit works pretty fine a a CISCO environment. If you have another manufacturer
you have to modify some parts of the lib.

And as always: Use at your own risk!
