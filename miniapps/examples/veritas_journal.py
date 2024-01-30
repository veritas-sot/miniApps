#!/usr/bin/env python

from veritas.journal import journal

config = {'running_config': 'jdfklsjdkljdkajdklas'}

my_journal = journal.Journal(id='test')
my_journal.add(log='hier passiert was', config=config)
my_journal.close()
