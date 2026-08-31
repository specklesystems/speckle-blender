"""Coordinate direct baking of a received :class:`specklepy.bundle.model.Model`.

The direct-bake receive path, modelled on Rhino's ``IArtifactHostObjectBuilder``:
parquet arrays go to ``bpy.data`` without ever being reconstituted into a Speckle
``Base`` graph. This module is the stable public seam; Blender construction and
repair algorithms live in the private ``_baking`` package.

The parse itself belongs to specklepy — ``bake_bundle`` consumes the SDK's
``Model`` facade directly (objects, nodes, relations, property views), and the
connector owns only the mapping onto ``bpy.data``.
"""

from __future__ import annotations

import bpy
from specklepy.bundle.model import Model

from ._baking.containers import build_containers, link_object_parts
from ._baking.geometry import GeometryBuilder
from ._baking.hierarchy import restore_subelements
from ._baking.instances import bake_placement, build_definitions, direct_placements
from ._baking.materials import build_materials
from ._baking.properties import apply_properties
from ._baking.result import BakeResult

__all__ = ["BakeResult", "bake_bundle"]


def bake_bundle(
    model: Model,
    root_collection_name: str,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> BakeResult:
    """Bake a whole received model into the current scene.

    Ordering is load-bearing: definitions must exist as collections before a
    placement can point an empty at one, and every object must exist before
    SUBELEMENT parenting can resolve both ends. Geometry is parsed lazily from
    the model's download directory, so the directory must still exist while
    this runs.
    """
    result = BakeResult()

    root_collection = bpy.data.collections.new(root_collection_name)
    bpy.context.scene.collection.children.link(root_collection)
    result.root_collection = root_collection

    materials = build_materials(model)
    containers = build_containers(model, root_collection, result)
    geometry_builder = GeometryBuilder(model, materials, result)

    definition_collections = build_definitions(model, geometry_builder)

    for obj in model.objects:
        placements = direct_placements(model, obj)
        if placements:
            built = bake_placement(
                obj.name or obj.application_id,
                placements,
                definition_collections,
                instance_loading_mode,
            )
        else:
            built = geometry_builder.build_object(obj)

        if not built:
            continue

        link_object_parts(model, obj, built, containers, root_collection)
        apply_properties(built[0], obj, result)
        result.objects[obj.application_id] = built[0]

    restore_subelements(model, result)
    return result
