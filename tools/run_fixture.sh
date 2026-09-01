#!/usr/bin/env bash
# Runs headless_export.py inside Blender. See tools/README.md.
#
#   tools/run_fixture.sh cube_with_props
#   tools/run_fixture.sh --all
#   tools/run_fixture.sh --blend ~/scenes/test.blend --objects Cube,Sphere
#
# Override the Blender binary with SPECKLE_BLENDER_BIN.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BLENDER="${SPECKLE_BLENDER_BIN:-}"
if [[ -z "$BLENDER" ]]; then
  for candidate in \
    /Applications/Blender.app/Contents/MacOS/Blender \
    "$(command -v blender 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then BLENDER="$candidate"; break; fi
  done
fi
if [[ -z "$BLENDER" ]]; then
  echo "Blender not found. Set SPECKLE_BLENDER_BIN to its path." >&2
  exit 127
fi

run_one() {
  # --factory-startup skips user prefs so the installed add-on can't shadow the
  # working tree; -noaudio keeps CI quiet. --python-exit-code is load-bearing:
  # without it Blender exits 0 when the script raises, and --all then reports
  # "All fixtures passed" against stale bundle dirs from an earlier run.
  "$BLENDER" --background --factory-startup -noaudio --python-exit-code 1 \
    --python "$REPO_ROOT/tools/headless_export.py" -- "$@" \
    2>&1 | grep -v '^Blender quit$'
  return "${PIPESTATUS[0]}"
}

if [[ "${1:-}" == "--all" ]]; then
  failed=()
  for fixture in "$REPO_ROOT"/tools/fixtures/*.py; do
    name="$(basename "$fixture" .py)"
    [[ "$name" == _* ]] && continue
    run_one --fixture "$name" || failed+=("$name")
  done
  echo
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "FAILED: ${failed[*]}"
    exit 1
  fi
  echo "All fixtures passed."
  exit 0
fi

# a bare first argument is a fixture name
if [[ $# -gt 0 && "$1" != --* ]]; then
  run_one --fixture "$@"
else
  run_one "$@"
fi
