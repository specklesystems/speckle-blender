"""Construct definition collections and bake their placements."""

from typing import Dict, List

import bpy
from mathutils import Matrix

from ..bundle_reader import BundleObject, ReceivedBundle
from .geometry import GeometryBuilder
from .transforms import placement_matrix


def build_definitions(
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


def bake_placement(
    obj: BundleObject,
    bundle: ReceivedBundle,
    definition_collections: Dict[int, bpy.types.Collection],
    instance_loading_mode: str,
) -> List[bpy.types.Object]:
    """Bake every placement of one object, primary first.

    One object can carry several placements: Revit atomizes a family instance
    into one DEFINITION/INSTANCE pair per material. Every placement bakes, and
    extras parent to the primary without reinterpreting their world matrices.
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
    """Recursively expand one placement into linked duplicates.

    Copies share member data-blocks. Nested collection instances are recursively
    expanded, while ``expanding`` protects against definition cycles.
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
