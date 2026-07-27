"""Speckle 4.0 parquet-bundle receive path (bundle -> Blender).

The mirror of ``converter/to_speckle/bundle_exporter.py``. Split in two on the
same line the publish side is split on, so most of it runs without Blender:

- ``bundle_reader`` — parquet tables -> plain dataclasses. No ``bpy``, so the
  harness can exercise it against a downloaded bundle offline.
- ``bundle_to_native`` — those dataclasses -> Blender data-blocks. Needs ``bpy``.
"""
