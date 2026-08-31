"""Construct definition collections and bake their placements."""

from typing import Dict, List

import bpy
from mathutils import Matrix
from specklepy.bundle.model import Model, ModelInstance, ModelObject

from .geometry import GeometryBuilder
from .transforms import placement_matrix


def direct_placements(model: Model, obj: ModelObject) -> List[ModelInstance]:
    """The placements this object draws through, via DISPLAY_INSTANCE, in ord
    order.

    Deliberately narrower than ``ModelObject.placements``, which also surfaces
    a PLACES edge — a definition member's own placement *inside* its
    definition. Baking that would draw a second, scene-level copy of something
    that only exists through the definition.

    A list, not a scalar: Revit atomizes a family instance into one
    DEFINITION/INSTANCE pair per material, so one object legitimately carries
    several placements. Blender's own publishes only ever write one.
    """
    ks = model.index.instances_by_object.get(obj.k) or []
    return [n for k in ks if isinstance(n := model.node(k), ModelInstance)]


def build_definitions(
    model: Model,
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
    if not model.definitions:
        return definition_collections

    rels = model.bundle.relations
    for definition in model.definitions:
        name = definition.name or f"Definition_{definition.k}"
        collection = bpy.data.collections.new(name)
        definition_collections[definition.k] = collection

        geometry_ks = rels.defines_by_definition.get(definition.k, [])
        ords = rels.defines_ord_by_definition.get(definition.k, [])
        members: Dict[int, List[int]] = {}
        for i, geometry_k in enumerate(geometry_ks):
            members.setdefault(ords[i] if i < len(ords) else 0, []).append(geometry_k)

        for ordinal in sorted(members):
            member_name = f"{name}.{ordinal}"
            for member in geometry_builder.build_definition_member(
                member_name, members[ordinal]
            ):
                collection.objects.link(member)

    # nested placements: a definition member that is itself an instance
    for definition in model.definitions:
        nested_ks = rels.defines_instance_by_definition.get(definition.k, [])
        for ordinal, instance_k in enumerate(nested_ks):
            instance = model.node(instance_k)
            if not isinstance(instance, ModelInstance):
                continue
            nested_definition = instance.definition
            if nested_definition is None:
                continue
            nested = definition_collections.get(nested_definition.k)
            if nested is None:
                continue
            empty = bpy.data.objects.new(f"{nested.name}.{ordinal}", None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = nested
            empty.matrix_world = placement_matrix(
                instance.transform or [], instance.units
            )
            definition_collections[definition.k].objects.link(empty)

    return definition_collections


def bake_placement(
    name: str,
    placements: List[ModelInstance],
    definition_collections: Dict[int, bpy.types.Collection],
    instance_loading_mode: str,
) -> List[bpy.types.Object]:
    """Bake every placement of one object, primary first.

    Every placement bakes, and extras parent to the primary without
    reinterpreting their world matrices.
    """
    built: List[bpy.types.Object] = []
    for instance in placements:
        definition = instance.definition
        if definition is None:
            continue
        collection = definition_collections.get(definition.k)
        if collection is None:
            continue
        matrix = placement_matrix(instance.transform or [], instance.units)
        if instance_loading_mode == "LINKED_DUPLICATES":
            built.extend(_duplicate_definition(name, collection, matrix, frozenset()))
        else:
            empty = bpy.data.objects.new(name, None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = collection
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
