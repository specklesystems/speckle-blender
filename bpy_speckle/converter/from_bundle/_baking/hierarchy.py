"""Restore final SUBELEMENT hierarchy after every object exists."""

from typing import List, Tuple

import bpy
from mathutils import Matrix

from ..bundle_reader import ReceivedBundle
from .result import BakeResult
from .transforms import origin_median, recenter_origin


def restore_subelements(bundle: ReceivedBundle, result: BakeResult) -> None:
    """Re-establish SUBELEMENT parenting once every object exists.

    Revit family subelements with geometry can be independent placements whose
    matrices are already world-space, so assigning a parent must not apply the
    parent's placement a second time. Properties-only siblings have no spatial
    placement of their own and remain identity-local so they follow their owner.

    A properties-only parent moves to the median of its placed children. Such a
    parent is anchored so a later bundle-order link preserves its established
    world position and the children already restored beneath it.
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
