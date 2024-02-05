########################
veritas quickstart Guide
########################

Installing the toolkit and the libary is easy. 

Requirements & Installation
***************************
As with many other Python applications, it is best to use a virtual environment for 
veritas and its toolkit. 

conda
=====

One option is to use (mini)conda. To install your virtual 
environment use:

.. code-block:: shell

    conda create --name veritas python=3.11 -yy
    conda activate veritas

You need poetry to install veritas.

.. code-block:: shell

    conda install poetry

The toolkit needs the veritas library to run. If you do not have installed the library already, 
download and install the library by running:

venv
====

.. code-block:: shell

    python -m venv veritas
    source veritas_env/bin/activate
    python -m pip install poetry

install veritas and its toolkit
===============================

.. code-block:: shell

    git clone https://github.com/veritas-sot/veritas.git
    cd veritas
    poetry install

Now clone and install the toolkit. Go to the directory in which the veritas subdirectory is located. Then:

.. code-block:: shell

    # go back to the upper directory if you installed veritas before
    cd ..

    git clone https://github.com/veritas-sot/miniApps.git
    cd miniApps
    poetry install

.. tip::

    To configure your miniApps have a look at the ./installation miniApp. Using this app you
    can configure all your miniApps within minutes. 

.. tip::

    If you are using a proxy, this may still need to be configured. The sytax to do this is:

    export HTTPS_PROXY=http://user:password@proxy:port/ 

Jupyter Notebooks
*****************

The toolkit provides a number of notebooks. Of course, jupyter must be installed in order to use them. 

.. code-block:: shell

    pip install jupyter
