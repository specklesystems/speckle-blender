from bpy.types import Object
from typing import Union, Optional, Tuple, List
from specklepy.objects.geometry import Polyline, Curve
from specklepy.objects.primitive import Interval
from specklepy.objects.base import Base
from mathutils import Matrix
from mathutils.geometry import interpolate_bezier
from .utils import nurb_make_curve, make_knots


def curve_to_speckle(
    blender_obj: Object, scale_factor: float = 1.0
) -> Union[Base, None]:
    assert blender_obj.type == "CURVE", "Object must be a curve"
    assert blender_obj.data is not None, "Curve data cannot be None"

    curve_data = blender_obj.data
    matrix = blender_obj.matrix_world
    units = "m"  # TODO: Use the unit system from the scene

    base = Base()
    curves = []

    for spline in curve_data.splines:
        if spline.type == "BEZIER":
            curves.append(
                bezier_to_speckle(matrix, spline, blender_obj.name, scale_factor, units)
            )
        elif spline.type == "NURBS":
            curves.append(
                nurbs_to_speckle(matrix, spline, blender_obj.name, scale_factor, units)
            )

    if curves:
        base["@elements"] = curves
        base["name"] = blender_obj.name
        return base

    return None


def bezier_to_speckle(
    matrix: Matrix,
    spline,
    name: Optional[str] = None,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Curve:
    degree = 3
    closed = spline.use_cyclic_u
    points: List[Tuple[float, float, float]] = []

    for i, bp in enumerate(spline.bezier_points):
        if i > 0:
            transformed_point = matrix @ bp.handle_left * scale_factor
            points.append(
                (transformed_point.x, transformed_point.y, transformed_point.z)
            )

        transformed_point = matrix @ bp.co * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

        if i < len(spline.bezier_points) - 1:
            transformed_point = matrix @ bp.handle_right * scale_factor
            points.append(
                (transformed_point.x, transformed_point.y, transformed_point.z)
            )

    if closed:
        transformed_point = (
            matrix @ spline.bezier_points[-1].handle_right * scale_factor
        )
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

        transformed_point = matrix @ spline.bezier_points[0].handle_left * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

        transformed_point = matrix @ spline.bezier_points[0].co * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

    num_points = len(points)

    flattened_points = []
    for point in points:
        flattened_points.extend(point)

    knot_count = num_points + degree - 1
    knots = [0] * knot_count

    for i in range(1, len(knots)):
        knots[i] = i // 3

    length = spline.calc_length()

    domain = Interval(start=0, end=length)
    display_value = bezier_to_speckle_polyline(
        matrix, spline, length, scale_factor, units
    )

    curve = Curve(
        degree=degree,
        periodic=not spline.use_endpoint_u,
        rational=True,
        points=flattened_points,
        weights=[1] * num_points,
        knots=knots,
        closed=spline.use_cyclic_u,
        displayValue=display_value,
        units=units,
        bbox=None,
    )

    curve.__dict__["_length"] = length
    curve.__dict__["_area"] = 0.0

    curve["domain"] = domain

    if name:
        curve["name"] = name

    return curve


def bezier_to_speckle_polyline(
    matrix: Matrix,
    spline,
    length: Optional[float] = None,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Optional[Polyline]:
    segments = len(spline.bezier_points)
    if segments < 2:
        return None

    resolution = spline.resolution_u + 1
    points: List[float] = []

    if not spline.use_cyclic_u:
        segments -= 1

    for i in range(segments):
        inext = (i + 1) % len(spline.bezier_points)

        knot1 = spline.bezier_points[i].co
        handle1 = spline.bezier_points[i].handle_right
        handle2 = spline.bezier_points[inext].handle_left
        knot2 = spline.bezier_points[inext].co

        sampled_points = interpolate_bezier(knot1, handle1, handle2, knot2, resolution)
        for p in sampled_points:
            scaled_point = matrix @ p * scale_factor
            points.append(scaled_point.x)
            points.append(scaled_point.y)
            points.append(scaled_point.z)

    length = length or spline.calc_length()

    polyline = Polyline(value=points, units=units)

    polyline["domain"] = {"start": 0, "end": length}
    polyline["closed"] = spline.use_cyclic_u

    return polyline


def nurbs_to_speckle(
    matrix: Matrix,
    spline,
    name: Optional[str] = None,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Curve:
    degree = spline.order_u - 1
    knots = make_knots(spline)

    length = spline.calc_length()
    domain = Interval(start=0, end=length)

    weights = [pt.weight for pt in spline.points]
    first_weight = weights[0] if weights else 1.0
    is_rational = any(abs(w - first_weight) > 1e-9 for w in weights)

    points = []
    for pt in spline.points:
        transformed_point = matrix @ pt.co.xyz * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

    flattened_points = []
    for point in points:
        flattened_points.extend(point)

    if spline.use_cyclic_u:
        for i in range(0, degree * 3, 3):
            flattened_points.append(flattened_points[i + 0])
            flattened_points.append(flattened_points[i + 1])
            flattened_points.append(flattened_points[i + 2])

        for i in range(0, degree):
            weights.append(weights[i])

    resolution_multiplier = (
        4 if (spline.use_cyclic_u and spline.point_count_u <= 16) else 1
    )
    display_value = nurbs_to_speckle_polyline(
        matrix, spline, length, scale_factor, units, resolution_multiplier
    )

    curve = Curve(
        degree=degree,
        periodic=not spline.use_endpoint_u,
        rational=is_rational,
        points=flattened_points,
        weights=weights,
        knots=knots,
        closed=spline.use_cyclic_u,
        displayValue=display_value,
        units=units,
        bbox=None,
    )

    curve.__dict__["_length"] = length

    curve["domain"] = domain

    if name:
        curve["name"] = name

    return curve


def nurbs_to_speckle_polyline(
    matrix: Matrix,
    spline,
    length: Optional[float] = None,
    scale_factor: float = 1.0,
    units: str = "m",
    resolution_multiplier: int = 1,
) -> Polyline:
    from mathutils import Vector

    points: List[float] = []

    resolution = spline.resolution_u * resolution_multiplier

    sampled_points = nurb_make_curve(spline, resolution)

    for i in range(0, len(sampled_points), 3):
        point_vector = Vector(
            (sampled_points[i], sampled_points[i + 1], sampled_points[i + 2])
        )
        transformed_point = matrix @ point_vector * scale_factor

        points.append(transformed_point.x)
        points.append(transformed_point.y)
        points.append(transformed_point.z)

    length = length or spline.calc_length()

    polyline = Polyline(value=points, units=units)

    polyline["domain"] = {"start": 0, "end": length}
    polyline["closed"] = spline.use_cyclic_u

    # Set length property if needed
    if hasattr(polyline, "length") or hasattr(polyline, "_length"):
        polyline.__dict__["_length"] = length

    # Set area property if needed
    if hasattr(polyline, "area") or hasattr(polyline, "_area"):
        polyline.__dict__["_area"] = 0

    return polyline
