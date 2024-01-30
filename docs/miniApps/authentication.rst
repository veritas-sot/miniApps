##############
Authentication
##############

.. contents::

Brief overview
**************
To login to your device you need a username and a password. veritas uses
a profile to store your credentials. To prevent your password from being 
clearly stored in a configuration, it is encrypted.

.. note::

    This encryption is not a secure. Do not use it on a productive system or 
    if you are not sure who has access to the profile.

.. note::

    To decrypt a token the three parameters ENCRYPTIONKEY, SALT and ITERATIONS 
    must equal to those values used to encrypt your password.

The parameters ENCRYPTIONKEY, SALT and ITERATIONS can either be configured using the
dotenv-mechnism (file .env) or can be configured using the arguments 
--encryptionkey --salt and --iterations.

Encrypt your password
*********************

.. code-block:: shell

    usage: encrypt_password.py [-h] [--salt SALT] [--encryptionkey ENCRYPTIONKEY] 
                               [--iterations ITERATIONS]

    options:
    -h, --help            show this help message and exit
    --salt SALT
    --encryptionkey ENCRYPTIONKEY
    --iterations ITERATIONS

Decrypt your password
*********************

.. code-block:: shell

    usage: decrypt_password.py [-h] [--salt SALT] [--encryptionkey ENCRYPTIONKEY] 
                               [--iterations ITERATIONS]

    options:
    -h, --help            show this help message and exit
    --salt SALT
    --encryptionkey ENCRYPTIONKEY
    --iterations ITERATIONS

Jupyter Notebooks
*****************
There are two jupyter nogtebooks to encrypt and decrypt your password.

.. code-block:: shell

    jupyter lab encrypt_password.ipynb
    jupyter lab decrypt_password.ipynb
