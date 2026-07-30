"""Build Blender collections and restore every container membership axis."""

from typing import Dict, List, Optional

import bpy

from ..bundle_reader import BundleObject, ReceivedBundle
from .result import BakeResult


def build_containers(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    result: BakeResult,
) -> Dict[int, bpy.types.Collection]:
    """Bake every CONTAINER axis to the documented Blender mapping.

    The spec's CONTAINER is polymorphic — its subtype picks the grouping axis,
    and each axis has its own membership relation. Blender has one grouping
    concept (the collection), but an object may live in many collections at
    once, which is exactly the multi-axis membership model:

    - ``Collection`` (IN_COLLECTION) — the authored tree, under the root.
    - ``Model`` (IN_MODEL) — the federation tier. One model maps onto the root;
      several become the outermost tier of collections, per the spec.
    - ``Group`` (IN_GROUP) — a ``Groups`` branch; objects multi-link in.
    - ``MEP System`` / ``Network`` (IN_SYSTEM) — a ``Systems`` branch, likewise.

    A subtype this mapping does not know is tallied on ``result`` and *not*
    baked — an empty folder would misread as "this grouping arrived intact".
    """
    created: Dict[int, bpy.types.Collection] = {}
    _build_collection_tree(bundle, root_collection, created)
    _build_model_tier(bundle, root_collection, created)
    _build_axis_branch(bundle, root_collection, created, {"Group"}, "Groups")
    _build_axis_branch(
        bundle, root_collection, created, {"MEP System", "Network"}, "Systems"
    )

    for container in bundle.containers.values():
        if container.node_id not in created:
            subtype = container.subtype or "(no subtype)"
            result.unmapped_containers[subtype] = (
                result.unmapped_containers.get(subtype, 0) + 1
            )
    return created


def _build_collection_tree(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Recreate the authored collection tree under ``root_collection``.

    The published root maps onto the caller's root rather than nesting inside it,
    so a load does not add a redundant folder level.
    """
    root_id = bundle.root_collection_id
    if root_id is not None:
        created[root_id] = root_collection

    def link_children(parent_id: Optional[int]) -> None:
        parent = created.get(parent_id, root_collection)
        for child in bundle.child_containers(parent_id):
            if not child.is_collection or child.node_id in created:
                continue
            collection = bpy.data.collections.new(child.name)
            parent.children.link(collection)
            created[child.node_id] = collection
            link_children(child.node_id)

    link_children(root_id)
    # Any collection not reachable from the root (a second parentless root, a
    # broken def_ref) still needs a home, or its objects would silently vanish.
    for node_id, child in bundle.containers.items():
        if child.is_collection and node_id not in created:
            collection = bpy.data.collections.new(child.name)
            root_collection.children.link(collection)
            created[node_id] = collection
            link_children(node_id)


def _build_model_tier(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Bake CONTAINER(Model) — the federation's source-file grouping.

    A single model maps onto the caller's root, mirroring how a lone authored
    root does; a real federation gets one collection per model under the root,
    the spec's "outermost scene-view tier when >1 model".
    """
    models = sorted(
        (c for c in bundle.containers.values() if c.subtype == "Model"),
        key=lambda c: c.node_id,
    )
    if not models:
        return
    if len(models) == 1:
        created[models[0].node_id] = root_collection
        return
    for model in models:
        collection = bpy.data.collections.new(model.name)
        root_collection.children.link(collection)
        created[model.node_id] = collection


def _build_axis_branch(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
    subtypes: set,
    branch_name: str,
) -> None:
    """Park one non-spatial grouping axis under a single branch collection.

    Groups and systems are membership *sets*, not a partition: an object keeps
    its authored collection and additionally links into each of these. Keeping
    the axis under one branch stops a Navis model's forty networks from reading
    as forty top-level folders. The branch only exists when the axis does, so a
    Blender-published bundle gains nothing.
    """
    members = {
        c.node_id: c for c in bundle.containers.values() if c.subtype in subtypes
    }
    if not members:
        return
    branch = bpy.data.collections.new(branch_name)
    root_collection.children.link(branch)

    def link(container, chain: frozenset) -> bpy.types.Collection:
        existing = created.get(container.node_id)
        if existing is not None:
            return existing
        # groups may nest via def_ref; a parent outside the axis (or a corrupt
        # def_ref cycle) tops out at the branch
        parent_container = members.get(container.parent_id)
        parent = branch
        if parent_container is not None and parent_container.node_id not in chain:
            parent = link(parent_container, chain | {container.node_id})
        collection = bpy.data.collections.new(container.name)
        parent.children.link(collection)
        created[container.node_id] = collection
        return collection

    for container in sorted(members.values(), key=lambda c: c.node_id):
        link(container, frozenset({container.node_id}))


def _primary_home(
    obj: BundleObject,
    containers: Dict[int, bpy.types.Collection],
    root_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    """The collection an object's scene-tree entry lives in.

    The authored collection wins when the producer sent one; a federated object
    without one sits in its model's tier; anything else lands at the root.
    """
    for node_id in (obj.collection_id, obj.model_id):
        home = containers.get(node_id) if node_id is not None else None
        if home is not None:
            return home
    return root_collection


def link_object_parts(
    obj: BundleObject,
    built: List[bpy.types.Object],
    containers: Dict[int, bpy.types.Collection],
    root_collection: bpy.types.Collection,
) -> None:
    """Link every built part into its spatial home and additive memberships."""
    target = _primary_home(obj, containers, root_collection)

    # the primary carries the object's identity; extra parts only appear for
    # mixed-family objects and are already parented to it
    for part in built:
        if part.name not in target.objects:
            target.objects.link(part)
    # group / system memberships are additive, not a move: the object stays
    # in its spatial home and also appears in each grouping it belongs to
    for extra_id in obj.group_ids + obj.system_ids:
        extra = containers.get(extra_id)
        if extra is None or extra is target:
            continue
        for part in built:
            if part.name not in extra.objects:
                extra.objects.link(part)
