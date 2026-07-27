"""Blender metaball families -> parent/child publish roles.

A metaball (``META``) object owns no surface of its own. Blender sums the scalar
fields of every metaball sharing a base name — ``Mball``, ``Mball.001``,
``Mball.007`` form one *family* — and polygonizes the combined isosurface onto a
single **basis** object. The other members evaluate to an empty mesh.

So the family, not the object, is the unit of geometry, and the resulting shape
is inseparable: the isosurface is continuous across contributors, and a single
triangle can straddle three elements' fields. There is no way, even in
principle, to ask Blender for "the mesh of ``Mball.001``".

That inverts the Revit curtain-wall pattern this borrows its wiring from. There
the parent is an empty container and the mullions and panels own the geometry;
here the basis owns *all* the geometry and the siblings own none. The edges are
the same either way — the basis becomes the family object and its siblings hang
off it as SUBELEMENT children carrying properties only, exactly as
``RevitArtifactRootObjectBuilder.EmitChild`` links a mullion to its wall.

Producing roles + a subelement table rather than emitting bundle edges directly
follows ``instance_unpacker``: the bundle exporter turns the table into
SUBELEMENT relations, while the classic JSON send simply carries the members as
ordinary geometry-less objects and stays round-trippable.

Blender's rules, confirmed against 4.3 rather than assumed:

- **Basis = lowest numeric suffix**, and an unsuffixed name sorts lowest. With
  only ``Blob.003``, ``Blob.001`` and ``Blob.007`` in the scene, ``Blob.001`` is
  the basis — a plain ``Blob`` need not exist.
- **A non-basis member evaluates to an empty mesh**, not an error.
- **The merged mesh is in the basis's local space**, siblings transformed into
  it, so baking the basis's ``matrix_world`` recovers world coordinates.
- **A viewport-hidden member contributes nothing** to the field.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import bpy
from bpy.types import Object

from .utils import get_object_id


def is_metaball(blender_object: Object) -> bool:
    return blender_object is not None and blender_object.type == "META"


def split_family_name(name: str) -> Tuple[str, int]:
    """``("Mball.007")`` -> ``("Mball", 7)``; an unsuffixed name sorts lowest.

    Mirrors Blender's own ``BLI_split_name_num``: the family key is everything
    before the *last* dot, and only an all-digit tail counts as a suffix, so an
    object genuinely named ``My.Blob`` keys on ``My.Blob`` rather than ``My``.
    """
    base, dot, tail = name.rpartition(".")
    if dot and tail.isdigit():
        return base, int(tail)
    return name, -1


@dataclass
class MetaballRole:
    """How one selected metaball participates in its family."""

    # the basis carries the merged blob; every other member is properties-only
    is_family_object: bool
    # object to tessellate through — the real basis, which may be unselected
    geometry_source: Optional[Object]
    family_name: str
    # every member of the family present in the scene, basis first
    member_count: int


@dataclass
class MetaballUnpackResult:
    """What the unpacker hands to the hierarchy builder."""

    roles: Dict[str, MetaballRole] = field(default_factory=dict)
    # family object applicationId -> its ordered SUBELEMENT children
    subelements: Dict[str, List[str]] = field(default_factory=dict)
    # families published through a member because the real basis was not
    # selected: the blob necessarily includes unselected siblings' contributions
    promoted_families: List[str] = field(default_factory=list)


def unpack_metaballs(selection: List[Object]) -> MetaballUnpackResult:
    """Group the selection's metaballs into families and assign publish roles.

    Family membership is scene-wide, so the basis is resolved against every
    metaball in the view layer — including ones the user did not select, because
    Blender polygonizes them into the blob regardless.
    """
    selected = [obj for obj in selection if is_metaball(obj)]
    if not selected:
        return MetaballUnpackResult()

    scene_families = _scene_families()
    selected_ids = {get_object_id(obj) for obj in selected}

    result = MetaballUnpackResult()
    by_family: Dict[str, List[Object]] = {}
    for obj in selected:
        by_family.setdefault(split_family_name(obj.name)[0], []).append(obj)

    for family_name, members in sorted(by_family.items()):
        # ordered the way Blender orders the family, so bundles diff stably
        # rather than following selection or iteration order
        members = sorted(members, key=lambda o: split_family_name(o.name)[1])
        # falls back to the selection when every scene member is hidden, so a
        # fully hidden family still resolves a basis instead of raising
        scene_members = scene_families.get(family_name) or members
        basis = scene_members[0]

        # The basis carries the geometry, but it need not be selected. Promote
        # the lowest-suffix *selected* member to publish the family, and still
        # tessellate through the real basis — that is the only object the
        # isosurface exists on.
        family_object = basis if get_object_id(basis) in selected_ids else members[0]
        if family_object is not basis:
            result.promoted_families.append(family_name)

        family_id = get_object_id(family_object)
        for obj in members:
            result.roles[get_object_id(obj)] = MetaballRole(
                is_family_object=obj is family_object,
                geometry_source=basis if obj is family_object else None,
                family_name=family_name,
                member_count=len(scene_members),
            )

        children = [get_object_id(o) for o in members if o is not family_object]
        if children:
            result.subelements[family_id] = children

    return result


def _scene_families() -> Dict[str, List[Object]]:
    """Every metaball in the view layer, grouped by family and basis-first.

    Uses the view layer rather than ``bpy.data`` so objects excluded from the
    depsgraph are not mistaken for the basis — they contribute no field, and
    tessellating through one would yield an empty mesh.
    """
    families: Dict[str, List[Object]] = {}
    view_layer = bpy.context.view_layer
    for obj in view_layer.objects:
        if not is_metaball(obj) or not obj.visible_get():
            continue
        families.setdefault(split_family_name(obj.name)[0], []).append(obj)

    for members in families.values():
        members.sort(key=lambda o: split_family_name(o.name)[1])
    return families
