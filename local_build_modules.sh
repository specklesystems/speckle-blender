#!/bin/sh

MODULES_PATH="./bpy_speckle/modules"

# Clean up
rm -rf $MODULES_PATH/*
rm -f requirements.txt

# Export poetry dependencies
poetry lock --no-update
poetry export -f requirements.txt --with dev --without-hashes > requirements.txt

# Install dependencies via pip
python -m pip install -r requirements.txt -t $MODULES_PATH