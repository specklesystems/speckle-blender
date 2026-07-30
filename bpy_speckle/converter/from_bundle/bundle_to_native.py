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

from typing import List, Tuple

import bpy
from mathutils import Matrix

from ._baking.containers import build_containers, link_object_parts
from ._baking.geometry import GeometryBuilder
from ._baking.instances import bake_placement, build_definitions
from ._baking.materials import build_materials
from ._baking.properties import apply_properties
from ._baking.result import BakeResult
from ._baking.transforms import (
    origin_median,
    recenter_origin,
)
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

    _parent_subelements(bundle, result)
    return result


def _parent_subelements(bundle: ReceivedBundle, result: BakeResult) -> None:
    """Re-establish SUBELEMENT parenting once every object exists.

    Revit family subelements with geometry can be independent placements whose
    matrices are already world-space, so assigning a parent must not apply the
    parent's placement a second time. Properties-only siblings have no spatial
    placement of their own and remain identity-local so they follow their owner,
    matching the original metaball-family behaviour.

    Both endpoints of every link get a meaningful origin first (see
    ``_recenter_origin``) — Blender draws relationship lines origin-to-origin,
    so world-baked endpoints left at the origin would each draw a line across
    the whole scene. A properties-only parent has no geometry to recentre onto
    and moves to the median of its placed children instead, taking its
    identity-local followers with it. A median-placed parent is *anchored*: if
    a later iteration links it as somebody's child, its world is preserved like
    a placed child's — following the new owner would drag the children already
    restored under it.
    """
    objects_by_id = bundle.objects_by_id()
    anchored: set = set()
    for obj in bundle.objects:
        if not obj.subelement_ids:
            continue
        parent = result.objects.get(obj.application_id)
        if parent is None:
            continue

        placed: List[Tuple[bpy.types.Object, Matrix]] = []
        followers: List[bpy.types.Object] = []
        for child_id in obj.subelement_ids:
            child = result.objects.get(child_id)
            if child is None or child is parent:
                continue
            child_obj = objects_by_id.get(child_id)
            if child in anchored or (
                child_obj and (child_obj.is_placement or child_obj.geometry_ks)
            ):
                recenter_origin(child)
                placed.append((child, child.matrix_world.copy()))
            else:
                followers.append(child)

        # the parent's origin must be final before any child is linked: a
        # child's world restore resolves against the parent's stored matrix
        recenter_origin(parent)
        if not obj.is_placement and not obj.geometry_ks and placed:
            parent.matrix_world = Matrix.Translation(
                origin_median([world.to_translation() for _, world in placed])
            )
            anchored.add(parent)

        for child, world_matrix in placed:
            child.parent = parent
            child.matrix_world = world_matrix
        for child in followers:
            child.parent = parent
