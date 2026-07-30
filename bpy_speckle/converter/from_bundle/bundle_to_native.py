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

from typing import Dict, List, Tuple

import bpy
from mathutils import Matrix

from ._baking.containers import build_containers, link_object_parts
from ._baking.geometry import GeometryBuilder
from ._baking.materials import build_materials
from ._baking.properties import apply_properties
from ._baking.result import BakeResult
from ._baking.transforms import (
    origin_median,
    placement_matrix,
    recenter_origin,
)
from .bundle_reader import BundleObject, ReceivedBundle

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

    definition_collections = _build_definitions(bundle, geometry_builder)

    for obj in bundle.objects:
        if obj.is_placement:
            built = _bake_placement(
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


def _build_definitions(
    bundle: ReceivedBundle,
    geometry_builder: GeometryBuilder,
) -> Dict[int, bpy.types.Collection]:
    """Turn each DEFINITION node into a collection of its member objects.

    Members are grouped by DEFINES ordinal — every geometry fragment of one
    member shares that member's ordinal, which is exactly what lets the
    fragments regroup into one object here. Definition collections are not
    linked into the scene; only placements reference them, which is what keeps
    an instanced "library" out of the visible scene tree.
    """
    definition_collections: Dict[int, bpy.types.Collection] = {}
    if not bundle.definitions:
        return definition_collections

    for node_id, definition in bundle.definitions.items():
        name = definition.name or f"Definition_{node_id}"
        collection = bpy.data.collections.new(name)
        definition_collections[node_id] = collection

        for ordinal in sorted(definition.members):
            member_name = f"{name}.{ordinal}"
            for member in geometry_builder.build_definition_member(
                member_name, definition.members[ordinal]
            ):
                collection.objects.link(member)

    # nested placements: a definition member that is itself an instance
    for node_id, definition in bundle.definitions.items():
        for ordinal, instance_id in definition.nested.items():
            instance = bundle.instances.get(instance_id)
            if instance is None or instance.def_ref is None:
                continue
            nested = definition_collections.get(instance.def_ref)
            if nested is None:
                continue
            empty = bpy.data.objects.new(f"{nested.name}.{ordinal}", None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = nested
            empty.matrix_world = placement_matrix(instance.transform, instance.units)
            definition_collections[node_id].objects.link(empty)

    return definition_collections


def _bake_placement(
    obj: BundleObject,
    bundle: ReceivedBundle,
    definition_collections: Dict[int, bpy.types.Collection],
    instance_loading_mode: str,
) -> List[bpy.types.Object]:
    """A collection instance: an empty pointing at the definition's collection.

    The publish side removed the collection's ``instance_offset`` from the
    placement transform and baked each member's ``matrix_world`` as
    definition-local geometry, so the transform applies here with no pivot
    correction — Blender's own offset is zero on a collection we created.

    One object can carry several placements: Revit atomizes a family instance
    into one DEFINITION/INSTANCE pair per material, so a chair arrives as a
    cushions placement plus a frame placement. Every placement bakes; the
    extras parent to the primary so the Outliner still reads as one element.
    Each empty keeps its own world transform — the atoms of one element share
    a transform in practice, but the bundle does not promise it, so parenting
    must not re-interpret the extras' matrices as primary-local.

    Returns the objects to link, primary first, like ``_bake_object`` — the
    caller owns collection membership, so linked-duplicate copies land in the
    model's collection alongside their parent rather than in the scene root.
    """
    name = obj.name or obj.application_id
    built: List[bpy.types.Object] = []
    for instance_id in obj.instance_ids:
        instance = bundle.instances.get(instance_id)
        if instance is None or instance.def_ref is None:
            continue
        definition = definition_collections.get(instance.def_ref)
        if definition is None:
            continue
        matrix = placement_matrix(instance.transform, instance.units)
        if instance_loading_mode == "LINKED_DUPLICATES":
            built.extend(_duplicate_definition(name, definition, matrix, frozenset()))
        else:
            empty = bpy.data.objects.new(name, None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = definition
            empty.matrix_world = matrix
            built.append(empty)

    # only batch roots are unparented here — linked-duplicate members already
    # hang off their own batch root with definition-local matrices
    primary_inverse = None
    for extra in built[1:]:
        if extra.parent is not None:
            continue
        if primary_inverse is None:
            primary_inverse = built[0].matrix_world.inverted(Matrix.Identity(4))
        extra.parent = built[0]
        extra.matrix_parent_inverse = primary_inverse
    return built


def _duplicate_definition(
    name: str,
    definition: bpy.types.Collection,
    matrix: Matrix,
    expanding: frozenset,
) -> List[bpy.types.Object]:
    """Expand one placement into a parent empty plus copies of the members.

    A copy shares its member's data-block — that is the "linked" in linked
    duplicates. A nested placement is the one member that must NOT be copied
    as-is: the copy would still be a COLLECTION-instance empty, leaving the
    nesting instanced when the user asked for editable objects. It is rebuilt
    instead as a plain empty whose children are themselves expanded copies, so
    the mode holds all the way down.

    ``expanding`` carries the definitions on the current expansion stack; a
    self-referential bundle (impossible from a real publisher, cheap to guard)
    stops instead of recursing forever.

    Transforms parent-chain: matrices here are definition-local ``matrix_basis``
    values, and only the outermost call passes a world-space placement — its
    empty has no parent, so basis and world coincide.
    """
    parent = bpy.data.objects.new(name, None)
    parent.matrix_basis = matrix
    built = [parent]
    if definition.name in expanding:
        return built
    expanding = expanding | {definition.name}

    for member in definition.objects:
        if member.instance_type == "COLLECTION" and member.instance_collection:
            children = _duplicate_definition(
                member.name, member.instance_collection, member.matrix_basis, expanding
            )
            children[0].parent = parent
            built.extend(children)
        else:
            copy = member.copy()
            copy.parent = parent
            # a mixed-family extra carries the parent inverse from its
            # in-definition parenting; under the batch root its basis alone is
            # the definition-local matrix
            copy.matrix_parent_inverse = Matrix.Identity(4)
            built.append(copy)
    return built


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
