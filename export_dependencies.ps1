#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

uv pip compile pyproject.toml --output-file bpy_speckle/requirements.txt --generate-hashes
