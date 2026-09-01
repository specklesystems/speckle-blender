"""Build Blender collections and restore every container membership axis."""

from typing import Dict, List, Optional

import bpy
from specklepy.bundle.model import Model, ModelContainer, ModelObject
from specklepy.bundle.spec import Rel

from .result import BakeResult


def _is_collection(container: ModelContainer) -> bool:
    """Part of the authored collection tree, as opposed to another axis."""
    return container.subtype == "Collection"


def _root_container(model: Model) -> Optional[ModelContainer]:
    """The authored collection root, selected by subtype — never row order.

    A cross-connector bundle can hold several parentless CONTAINERs at once
    (each model, system and top-level group is the root of its own axis), so
    "first parentless row" would crown whichever axis the producer happened
    to write first. Only ``Collection`` containers qualify; ties break on the
    lowest node id so the choice is deterministic. ``None`` when the bundle
    has no authored collections at all (a bare Navis federation, say).
    """
    roots = [c for c in model.collections if c.parent is None and _is_collection(c)]
    return min(roots, key=lambda c: c.k) if roots else None


def build_containers(
    model: Model,
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
    _build_collection_tree(model, root_collection, created)
    _build_model_tier(model, root_collection, created)
    _build_axis_branch(model, root_collection, created, {"Group"}, "Groups")
    _build_axis_branch(
        model, root_collection, created, {"MEP System", "Network"}, "Systems"
    )

    for container in model.collections:
        if container.k not in created:
            subtype = container.subtype or "(no subtype)"
            result.unmapped_containers[subtype] = (
                result.unmapped_containers.get(subtype, 0) + 1
            )
    return created


def _new_collection(container: ModelContainer) -> bpy.types.Collection:
    return bpy.data.collections.new(container.name or f"Collection_{container.k}")


def _build_collection_tree(
    model: Model,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Recreate the authored collection tree under ``root_collection``.

    The published root maps onto the caller's root rather than nesting inside it,
    so a load does not add a redundant folder level.
    """
    root = _root_container(model)
    if root is not None:
        created[root.k] = root_collection

    def link_children(parent: ModelContainer, parent_bcoll) -> None:
        for child in parent.children:
            if not _is_collection(child) or child.k in created:
                continue
            collection = _new_collection(child)
            parent_bcoll.children.link(collection)
            created[child.k] = collection
            link_children(child, collection)

    if root is not None:
        link_children(root, root_collection)
    # Any collection not reachable from the root (a second parentless root, a
    # broken def_ref) still needs a home, or its objects would silently vanish.
    for container in model.collections:
        if _is_collection(container) and container.k not in created:
            collection = _new_collection(container)
            root_collection.children.link(collection)
            created[container.k] = collection
            link_children(container, collection)


def _build_model_tier(
    model: Model,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Bake CONTAINER(Model) — the federation's source-file grouping.

    A single model maps onto the caller's root, mirroring how a lone authored
    root does; a real federation gets one collection per model under the root,
    the spec's "outermost scene-view tier when >1 model".
    """
    models = [c for c in model.collections if c.subtype == "Model"]
    if not models:
        return
    if len(models) == 1:
        created[models[0].k] = root_collection
        return
    for tier in models:
        collection = _new_collection(tier)
        root_collection.children.link(collection)
        created[tier.k] = collection


def _build_axis_branch(
    model: Model,
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
    members = {c.k: c for c in model.collections if c.subtype in subtypes}
    if not members:
        return
    branch = bpy.data.collections.new(branch_name)
    root_collection.children.link(branch)

    def link(container: ModelContainer, chain: frozenset) -> bpy.types.Collection:
        existing = created.get(container.k)
        if existing is not None:
            return existing
        # groups may nest via def_ref; a parent outside the axis (or a corrupt
        # def_ref cycle) tops out at the branch
        parent_container = (
            members.get(container.parent.k) if container.parent is not None else None
        )
        parent = branch
        if parent_container is not None and parent_container.k not in chain:
            parent = link(parent_container, chain | {container.k})
        collection = _new_collection(container)
        parent.children.link(collection)
        created[container.k] = collection
        return collection

    for container in members.values():
        link(container, frozenset({container.k}))


def _primary_home(
    model: Model,
    obj: ModelObject,
    containers: Dict[int, bpy.types.Collection],
    root_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    """The collection an object's scene-tree entry lives in.

    The authored collection wins when the producer sent one; a federated object
    without one sits in its model's tier; anything else lands at the root.
    """
    collection = obj.collection
    if collection is not None:
        home = containers.get(collection.k)
        if home is not None:
            return home
    in_model = model.bundle.relations.object_node_by_rel.get(int(Rel.IN_MODEL), {})
    home = containers.get(in_model.get(obj.k, -1))
    return home if home is not None else root_collection


def link_object_parts(
    model: Model,
    obj: ModelObject,
    built: List[bpy.types.Object],
    containers: Dict[int, bpy.types.Collection],
    root_collection: bpy.types.Collection,
) -> None:
    """Link every built part into its spatial home and additive memberships."""
    target = _primary_home(model, obj, containers, root_collection)

    # group / system memberships are additive, not a move: the object stays in
    # its spatial home and also appears in each grouping it belongs to. The SDK
    # reads IN_SYSTEM as single-valued (last edge wins); restoring overlapping
    # system membership needs a specklepy change, not a shim here.
    extras = [group.k for group in obj.groups]
    if obj.system is not None:
        extras.append(obj.system.k)

    # the primary carries the object's identity; extra parts only appear for
    # mixed-family objects and are already parented to it
    for part in built:
        if part.name not in target.objects:
            target.objects.link(part)
    for extra_k in extras:
        extra = containers.get(extra_k)
        if extra is None or extra is target:
            continue
        for part in built:
            if part.name not in extra.objects:
                extra.objects.link(part)
