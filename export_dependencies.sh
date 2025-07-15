#!/usr/bin/env bash
set -e -o pipefail

uv pip compile pyproject.toml --output-file bpy_speckle/requirements.txt --generate-hashes
