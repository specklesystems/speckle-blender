"""Blender collection instances -> Speckle instance/definition proxies.

The direct analogue of ``RhinoInstanceUnpacker`` in speckle-sharp-connectors: it
walks the publish selection, turns every collection-instance EMPTY into an
``InstanceProxy`` + ``InstanceDefinitionProxy`` pair, and pulls the instanced
collection's members into the conversion set so their geometry ships once, in
definition-local coordinates.

Producing proxies rather than emitting bundle nodes directly keeps this
unpacker free of bundle vocabulary: ``BlenderBundleExporter`` translates the
proxies into DEFINITION/INSTANCE nodes. Same split as the C# connectors.

Two Blender-specific wrinkles:

- **instance_offset.** Blender places an instanced member at
  ``empty.matrix_world @ Translation(-collection.instance_offset) @ member.matrix_world``.
  The members already bake their own ``matrix_world`` as definition-local
  geometry, so the collection's pivot has to be divided back out of the
  placement transform rather than added to the members.
- **Definition members are usually real scene objects too.** Unlike a Rhino
  block definition, the instanced collection normally still lives in the scene.
  So a member is only suppressed from the scene tree when the user did *not*
  independently select it — see ``definition_only_ids``.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set

from bpy.types import Collection as BCollection
from bpy.types import Object
from mathutils import Matrix as MMatrix
from mathutils import Vector as MVector

from specklepy.objects.proxies import InstanceDefinitionProxy, InstanceProxy

from .utils import get_object_id, get_unique_id


def is_collection_instance(blender_object: Object) -> bool:
    """True for an EMPTY that places a collection (Blender's block instance)."""
    return (
        blender_object.type == "EMPTY"
        and blender_object.instance_type == "COLLECTION"
        and blender_object.instance_collection is not None
    )


def get_definition_id(collection: BCollection) -> str:
    return get_unique_id(collection)


@dataclass
class InstanceUnpackResult:
    """What the unpacker hands to the hierarchy builder."""

    # the publish selection plus every definition member pulled in behind it,
    # selection first and in order, so existing conversion stays deterministic
    objects: List[Object] = field(default_factory=list)
    # object applicationId -> its placement proxy
    instance_proxies: Dict[str, InstanceProxy] = field(default_factory=dict)
    definition_proxies: List[InstanceDefinitionProxy] = field(default_factory=list)
    # members that render ONLY through a placement: they get no IN_COLLECTION and
    # no DISPLAY of their own. A member the user also selected is absent here — it
    # is a real scene object that a definition happens to reference as well.
    definition_only_ids: Set[str] = field(default_factory=set)


class InstanceUnpacker:
    def __init__(self, units: str, scale_factor: float = 1.0) -> None:
        self._units = units
        self._scale_factor = scale_factor
        self._objects: List[Object] = []
        self._seen_object_ids: Set[str] = set()
        self._instance_proxies: Dict[str, InstanceProxy] = {}
        self._definitions: Dict[str, InstanceDefinitionProxy] = {}
        self._proxies_by_definition: Dict[str, List[InstanceProxy]] = {}
        self._member_ids: Set[str] = set()

    def unpack_selection(self, selection: List[Object]) -> InstanceUnpackResult:
        selected_ids = {get_object_id(obj) for obj in selection if obj}

        for blender_object in selection:
            if not blender_object:
                continue
            if is_collection_instance(blender_object):
                self._unpack_instance(blender_object)
            self._add_atomic(blender_object)

        return InstanceUnpackResult(
            objects=self._objects,
            instance_proxies=self._instance_proxies,
            definition_proxies=list(self._definitions.values()),
            # a member the user selected in its own right stays a scene object
            definition_only_ids=self._member_ids - selected_ids,
        )

    # ── internals ───────────────────────────────────────────────────────────

    def _add_atomic(self, blender_object: Object) -> None:
        """Register an object for conversion, once, preserving first-seen order."""
        object_id = get_object_id(blender_object)
        if object_id in self._seen_object_ids:
            return
        self._seen_object_ids.add(object_id)
        self._objects.append(blender_object)

    def _unpack_instance(self, empty: Object, depth: int = 0) -> None:
        collection = empty.instance_collection
        instance_id = get_object_id(empty)
        definition_id = get_definition_id(collection)

        self._instance_proxies[instance_id] = InstanceProxy(
            applicationId=instance_id,
            definitionId=definition_id,
            transform=self._placement_transform(empty, collection),
            maxDepth=depth,
            units=self._units,
        )

        # Every placement of a definition records the deepest nesting that definition
        # is seen at, so receive can rebuild definitions before the instances that
        # need them (descending maxDepth). Same bookkeeping as RhinoInstanceUnpacker.
        siblings = self._proxies_by_definition.setdefault(definition_id, [])
        for sibling in siblings:
            if sibling.maxDepth < depth:
                sibling.maxDepth = depth
        siblings.append(self._instance_proxies[instance_id])

        existing = self._definitions.get(definition_id)
        if existing is not None:
            # already walked; only its depth can still deepen
            if existing.maxDepth < depth:
                existing.maxDepth = depth
            return

        definition = InstanceDefinitionProxy(
            applicationId=definition_id,
            objects=[],
            maxDepth=depth,
            name=collection.name,
        )
        # register before recursing so a collection reachable from itself terminates
        self._definitions[definition_id] = definition

        # all_objects, not objects: Blender renders a nested sub-collection's
        # contents as part of the instance, and a DEFINITION has no inner tree to
        # mirror that with — it is a flat list of members.
        for member in collection.all_objects:
            member_id = get_object_id(member)
            definition.objects.append(member_id)
            self._member_ids.add(member_id)
            if is_collection_instance(member):
                self._unpack_instance(member, depth + 1)
            self._add_atomic(member)

    def _placement_transform(
        self, empty: Object, collection: BCollection
    ) -> List[float]:
        """Row-major 4x4 mapping definition-local coordinates to world.

        ``instance_offset`` is the collection's pivot: Blender bakes it into where
        the empty draws its contents, so it comes back out here. The translation
        column is scaled to match the geometry, which conversion already multiplied
        by the scene's unit scale.
        """
        matrix = empty.matrix_world @ MMatrix.Translation(
            -MVector(collection.instance_offset)
        )
        rows = [list(row) for row in matrix]
        for row in rows[:3]:
            row[3] *= self._scale_factor
        return [value for row in rows for value in row]


def unpack_instances(
    selection: List[Object], units: str, scale_factor: float = 1.0
) -> InstanceUnpackResult:
    """Expand a publish selection with the collection instances it contains."""
    return InstanceUnpacker(units, scale_factor).unpack_selection(selection)
