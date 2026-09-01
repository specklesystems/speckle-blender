"""Convert Blender Curve objects to Speckle geometry.

A Blender curve is really two things at once: a path (the splines the user
edits) and, when the shape settings give it a cross-section, the swept surface
Blender generates from that path at display time. Only the path exists as data
— the tube, the extrusion and the filled cap are produced by the tessellator
and are not recoverable from ``curve_data.splines``.

So this module picks a representation per object: curves whose shape settings
produce faces are published as meshes (via ``to_mesh()``, the same route text
takes), and genuine wire curves keep their exact NURBS/Bezier definition.
"""

from bpy.types import Curve as BCurve
from bpy.types import Object
from typing import Union, Optional, Tuple, List
from specklepy.objects.geometry import Polyline, Curve
from specklepy.objects.geometry.mesh import Mesh
from specklepy.objects.primitive import Interval
from specklepy.objects.base import Base
from mathutils import Matrix
from mathutils.geometry import interpolate_bezier
from .mesh_to_speckle import mesh_to_speckle_meshes
from .utils import (
    nurb_make_curve,
    make_knots,
    apply_cached_properties,
    extract_custom_properties,
    get_curve_element_id,
    temporary_mesh,
)


def curve_may_have_volume(curve_data: BCurve) -> bool:
    """Whether the curve's shape settings could make Blender generate faces.

    Deliberately over-inclusive: it exists only to skip the cost of
    tessellating the common case (a plain wire curve). Whether faces are
    *actually* produced is settled by asking Blender — see
    ``curve_to_speckle_display_value`` — so a false positive here costs one
    throwaway ``to_mesh()`` and nothing else.

    The cases, all of them properties on the Curve datablock rather than
    modifiers, which is why the modifier-only check they used to sit behind
    never caught them:
      - ``bevel_depth``  — a round or custom-profile cross-section swept along
        the path (``bevel_mode`` of ``ROUND`` or ``PROFILE``)
      - ``bevel_object`` — another curve used as the cross-section
                           (``bevel_mode`` of ``OBJECT``)
      - ``extrude``      — the path pushed along local Z into a ribbon or solid
      - a 2D curve with a ``fill_mode`` other than ``NONE``, which caps closed
        splines with a flat face
    """
    if curve_data.bevel_depth != 0.0 or curve_data.bevel_object is not None:
        return True

    if curve_data.extrude != 0.0:
        return True

    return curve_data.dimensions == "2D" and curve_data.fill_mode != "NONE"


def curve_to_speckle_display_value(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> List[Base]:
    """Build the ``displayValue`` for a Blender Curve object.

    Returns meshes when the curve renders as a solid and Speckle curves when it
    is a wire. Returns an empty list when there is nothing to publish, which
    makes ``convert_to_speckle`` drop the object.
    """
    assert blender_object.type == "CURVE", "Object must be a curve"
    assert blender_object.data is not None, "Curve data cannot be None"

    curve_data: BCurve = blender_object.data
    has_modifiers = bool(apply_modifiers and blender_object.modifiers)

    if has_modifiers or curve_may_have_volume(curve_data):
        meshes = tessellated_curve_to_speckle_meshes(
            blender_object, curve_data, scale_factor, units, apply_modifiers
        )
        if meshes:
            return list(meshes)
        # no faces after all — the shape settings were set but inert (an open
        # spline with fill only, a zero-radius bevel object), so fall through
        # and publish the path

    return curve_splines_to_speckle(blender_object, curve_data, scale_factor)


def tessellated_curve_to_speckle_meshes(
    blender_object: Object,
    curve_data: BCurve,
    scale_factor: float,
    units: str,
    apply_modifiers: bool,
) -> List[Mesh]:
    """Convert the curve's generated surface to Speckle meshes, one per material
    slot. Empty when Blender tessellates the curve to no faces."""
    with temporary_mesh(blender_object, apply_modifiers) as mesh:
        if mesh is None or not mesh.polygons:
            return []

        meshes = mesh_to_speckle_meshes(blender_object, mesh, scale_factor, units)

    # the tessellated mesh is a throwaway datablock, so any custom properties
    # the user set live on the Curve — carry them onto the geometry the way the
    # wire path below carries them onto each spline
    curve_properties = extract_custom_properties(curve_data)
    for speckle_mesh in meshes:
        apply_cached_properties(speckle_mesh, curve_properties)

    return meshes


def curve_splines_to_speckle(
    blender_object: Object, curve_data: BCurve, scale_factor: float
) -> List[Base]:
    """Convert each spline of a wire curve to its Speckle equivalent, preserving
    the exact NURBS/Bezier definition."""
    result = curve_to_speckle(blender_object, scale_factor)
    if result is None:
        return []

    elements = result["@elements"] if hasattr(result, "@elements") else [result]
    for i, element in enumerate(elements):
        if hasattr(element, "applicationId"):
            element.applicationId = get_curve_element_id(blender_object, i)

    return elements


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

    # extract custom properties once for all curves (shared curve data)
    curve_properties = extract_custom_properties(curve_data)

    for spline in curve_data.splines:
        if spline.type == "BEZIER":
            curve = bezier_to_speckle(
                matrix, spline, blender_obj.name, scale_factor, units
            )
            apply_cached_properties(curve, curve_properties)
            curves.append(curve)
        elif spline.type == "NURBS":
            curve = nurbs_to_speckle(
                matrix, spline, blender_obj.name, scale_factor, units
            )
            apply_cached_properties(curve, curve_properties)
            curves.append(curve)

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
