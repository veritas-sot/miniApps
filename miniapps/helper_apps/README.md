This directory contains some helper apps.

get_unique_set_of_locations.py

This app reads a xlsx file containing locations and writes a xlsx file
that containes a unique set of locations that can be imported by kobold

input:

The xlsx file contains rows describing a location like

country, city, brach, building, floor, section, room

Please note: This script assumes that col x is the parent of col x+1

output:

name                    name of the element
parent.name             the parent or root if it has no parent
location_type.name      the type of the location like country, city, ...
status.name             is always set to Active

