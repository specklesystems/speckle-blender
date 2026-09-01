"""Shared spatial conventions for direct bundle baking."""

from typing import List, Optional, Tuple

import bpy
from mathutils import Matrix
from specklepy.objects.models.units import (
    get_scale_factor_to_meters,
    get_units_from_string,
)


def scale_for(units: Optional[str]) -> float:
    """Scale factor from a bundle unit string into the Blender scene."""
    if not units:
        return 1.0
    unit_scale = get_scale_factor_to_meters(get_units_from_string(units))
    return unit_scale / bpy.context.scene.unit_settings.scale_length


def placement_matrix(transform: List[float], units: Optional[str]) -> Matrix:
    """Turn a placement's 16 row-major doubles into a Blender matrix.

    The translation is unit-scaled but the rotation/shear block is not — scaling
    the whole matrix would scale the basis vectors too and shrink the instance.
    """
    if len(transform) != 16:
        return Matrix.Identity(4)
    matrix = Matrix([transform[0:4], transform[4:8], transform[8:12], transform[12:16]])
    scale = scale_for(units)
    if scale != 1.0:
        for row in range(3):
            matrix[row][3] *= scale
    return matrix


def _local_bounds_center(data: object) -> Optional[Tuple[float, float, float]]:
    """Bounds center of a mesh or curve data-block, in its own coordinates.

    Computed from the data directly — ``Object.bound_box`` is only valid after
    a depsgraph evaluation, which freshly created objects have not had.
    """
    if isinstance(data, bpy.types.Mesh):
        count = len(data.vertices)
        if not count:
            return None
        flat = [0.0] * (count * 3)
        data.vertices.foreach_get("co", flat)
        xs, ys, zs = flat[0::3], flat[1::3], flat[2::3]
    elif isinstance(data, bpy.types.Curve):
        xs, ys, zs = [], [], []
        for spline in data.splines:
            points = spline.bezier_points if spline.type == "BEZIER" else spline.points
            for point in points:
                co = point.co
                xs.append(co[0])
                ys.append(co[1])
                zs.append(co[2])
        if not xs:
            return None
    else:
        return None
    return (
        (min(xs) + max(xs)) / 2.0,
        (min(ys) + max(ys)) / 2.0,
        (min(zs) + max(zs)) / 2.0,
    )


def recenter_origin(obj: bpy.types.Object) -> None:
    """Move a world-baked object's origin onto its geometry's bounds center.

    Direct-baked data carries world coordinates under an identity matrix, so
    every object's origin sits at (0, 0, 0). That is invisible until the object
    joins a parent relationship: Blender draws relationship lines
    origin-to-origin, so a placed child linked to an origin-bound parent draws
    a line across the whole scene. Only parenting participants are recentred;
    everything else keeps the identity transform the dialect promises.

    World geometry is preserved exactly — the data shifts by ``-center`` and
    the matrix gains ``+center``. Recentring twice is a no-op (the second
    center is ~zero), and shared data is left alone: shifting it would move
    every other user.
    """
    data = obj.data
    if data is None or data.users > 1:
        return
    center = _local_bounds_center(data)
    if center is None or max(abs(c) for c in center) < 1e-9:
        return
    data.transform(Matrix.Translation((-center[0], -center[1], -center[2])))
    obj.matrix_world = obj.matrix_world @ Matrix.Translation(center)


def origin_median(origins: List[object]) -> Tuple[float, float, float]:
    """Component-wise median — resists the one far-flung subelement."""

    def median(values: List[float]) -> float:
        values = sorted(values)
        mid = len(values) // 2
        if len(values) % 2:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2.0

    return (
        median([o[0] for o in origins]),
        median([o[1] for o in origins]),
        median([o[2] for o in origins]),
    )
