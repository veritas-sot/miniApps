#!/usr/bin/env python

from loguru import logger
from veritas.journal import journal


def main():

    jrnl = journal.Journal()
    uuid = jrnl.new()

    id = jrnl.message(app='backup', message='backup all devices')

    # write cron

    jrnl.close()

if __name__ == "__main__":
    main()
