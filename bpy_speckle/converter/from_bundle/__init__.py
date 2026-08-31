"""Artifact-bundle receive path (specklepy ``Model`` -> Blender).

The mirror of ``converter/to_speckle/bundle_exporter.py``. Download and parse
belong to specklepy (``bundle.download``, ``bundle.bundle_reader``, the
``Model`` facade); this package owns only the bake:

- ``bundle_to_native`` — the stable public ``bake_bundle(model, ...)``
  coordinator and the ``BakeResult`` export. Needs ``bpy``.
- ``_baking`` — private, focused Blender construction modules for geometry,
  materials, containers, properties, instances, transforms, and hierarchy.
"""
