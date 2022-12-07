#!/usr/bin/env bash
set -e -o pipefail

poetry export --only main -o bpy_speckle/requirements.txt
