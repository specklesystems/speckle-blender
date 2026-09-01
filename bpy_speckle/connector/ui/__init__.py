"""Panels and dialogs (SPECKLE_PT_*, SPECKLE_OT_*).

Deliberately no re-exports. ``bpy_speckle/__init__.py`` imports
``connector.ui.icons`` *before* ``ensure_dependencies()`` runs, so this file
executes pre-bootstrap: any re-export whose module (transitively) imports
specklepy would crash the add-on before it can install its own dependencies.
Import dialog and panel classes from their modules directly.
"""
