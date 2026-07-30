"""Bakes a parsed bundle straight into Blender data-blocks.

The direct-bake receive path, modelled on Rhino's ``IArtifactHostObjectBuilder``:
parquet arrays go to ``bpy.data`` without ever being reconstituted into a Speckle
``Base`` graph. Publishing already wrote world-baked geometry (Blender's
direct-display dialect), so a mesh's coordinates are final — the object is
created at the origin with the mesh carrying its own world position, exactly
inverting ``mesh_to_speckle_meshes``. Objects that join a parent relationship
(SUBELEMENT hierarchies, mixed-family extras) are recentred onto their geometry
(``_recenter_origin``), world position unchanged, so viewport relationship
lines don't all converge on the origin.

Collection instances are the one exception, as they are on the publish side: an
INSTANCE node becomes an empty with ``instance_type = 'COLLECTION'`` pointing at
the definition's collection, and the placement transform goes on the empty.
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

# ── orchestration ───────────────────────────────────────────────────────────


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
