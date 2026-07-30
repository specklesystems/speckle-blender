"""Speckle 4.0 parquet-bundle receive path (bundle -> Blender).

The mirror of ``converter/to_speckle/bundle_exporter.py``. Split on the same
line as the publish side, so most of it runs without Blender:

- ``bundle_reader`` — parquet tables -> plain dataclasses. No ``bpy``, so the
  harness can exercise it against a downloaded bundle offline.
- ``bundle_to_native`` — the stable public ``bake_bundle`` coordinator and
  ``BakeResult`` compatibility export. Needs ``bpy``.
- ``_baking`` — private, focused Blender construction modules for geometry,
  materials, containers, properties, instances, transforms, and hierarchy.
"""
