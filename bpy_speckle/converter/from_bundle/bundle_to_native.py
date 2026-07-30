"""Coordinate direct baking of a parsed bundle into Blender data-blocks.

The direct-bake receive path, modelled on Rhino's ``IArtifactHostObjectBuilder``:
parquet arrays go to ``bpy.data`` without ever being reconstituted into a Speckle
``Base`` graph. This module is the stable public seam; Blender construction and
repair algorithms live in the private ``_baking`` package.
"""

from __future__ import annotations

import bpy

from ._baking.containers import build_containers, link_object_parts
from ._baking.geometry import GeometryBuilder
from ._baking.hierarchy import restore_subelements
from ._baking.instances import bake_placement, build_definitions
from ._baking.materials import build_materials
from ._baking.properties import apply_properties
from ._baking.result import BakeResult
from .bundle_reader import ReceivedBundle

__all__ = ["BakeResult", "bake_bundle"]


def bake_bundle(
    bundle: ReceivedBundle,
    root_collection_name: str,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> BakeResult:
    """Bake a whole bundle into the current scene.

    Ordering is load-bearing: definitions must exist as collections before a
    placement can point an empty at one, and every object must exist before
    SUBELEMENT parenting can resolve both ends.
    """
    result = BakeResult()

    root_collection = bpy.data.collections.new(root_collection_name)
    bpy.context.scene.collection.children.link(root_collection)
    result.root_collection = root_collection

    materials = build_materials(bundle)
    containers = build_containers(bundle, root_collection, result)
    geometry_builder = GeometryBuilder(bundle, materials, result)

    definition_collections = build_definitions(bundle, geometry_builder)

    for obj in bundle.objects:
        if obj.is_placement:
            built = bake_placement(
                obj, bundle, definition_collections, instance_loading_mode
            )
        else:
            built = geometry_builder.build_object(obj)

        if not built:
            continue

        link_object_parts(obj, built, containers, root_collection)
        apply_properties(built[0], obj, result)
        result.objects[obj.application_id] = built[0]

    restore_subelements(bundle, result)
    return result
