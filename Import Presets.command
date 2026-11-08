#!/bin/bash
# Double-click in Finder to run the importer; it asks for the preset folder.
cd "$(dirname "$0")" || exit 1
clear
python3 import_presets.py
