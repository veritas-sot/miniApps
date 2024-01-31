########################
veritas quickstart Guide
########################

Installing the toolkit and the libary is easy. 

Requirements & Installation
***************************

As with many other Python applications, it is best to use a virtual environment for 
veritas and its toolkit. One option is to use (mini)conda. To install your virtual 
environment use:

.. code-block:: shell

    conda create --name veritas python=3.11 -yy
    conda activate veritas

You need poetry to install veritas.

.. code-block:: shell

    pip install poetry

The toolkit needs the veritas library to run. If you do not have installed the library already, 
download and install the library by running:

.. code-block:: shell

    # go back to the upper directory
    cd ..
    git clone https://github.com/veritas-sot/veritas.git
    cd veritas
    poetry install

Now clone and install the toolkit. Go to the directory in which the veritas subdirectory is located. Then:

.. code-block:: shell

    git clone https://github.com/veritas-sot/miniApps.git
    cd miniApps
    poetry install

.. tip::

    To configure your miniApps have a look at the ./installtion miniApp. Using this app you
    can configure all your miniApps within minutes. 

Jupyter Notebooks
*****************

The toolkit provides a number of notebooks. Of course, jupyter must be installed in order to use them. 

.. code-block:: shell

    pip install jupyter
