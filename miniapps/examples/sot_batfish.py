#!/usr/bin/env python

import json
import logging
import yaml
import urllib3
from veritas.sot import sot

# to disable warning if TLS warning is written to console
urllib3.disable_warnings()

log_format = '%(asctime)s %(levelname)s:%(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format)

sot = sot.Sot(token="your_token", 
              ssl_verify=False,
              url=__URL__)

# long version
# cls = getattr(sot.registry('analyzer'),'Analyzer')
# analyzer = cls(sot, 'lab.local')
# or even shorter
analyzer = getattr(sot.registry('analyzer'),'Analyzer')(sot, 'lab.local')
analyzer = analyzer.get_init_issues()
analyzer.analyse()
