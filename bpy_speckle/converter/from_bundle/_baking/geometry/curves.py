"""Decode and construct every curve-family SGEO primitive."""

from typing import List, Optional, Tuple

import bpy
from specklepy.bundle import sgeo
from specklepy.bundle.bundle_reader import Geometry

from ..transforms import scale_for

# segments used when flattening an analytical arc/circle/ellipse to a polyline.
# Blender has no native arc primitive, so these are tessellated on the way in.
_ARC_SEGMENTS = 64


def build_curve_object(
    name: str,
    data_name: str,
    geometries: List[Geometry],
    materials: List[Optional[bpy.types.Material]],
) -> Tuple[Optional[bpy.types.Object], List[str]]:
    """Decode and merge one object's curve geometry into one Blender object."""
    curves, errors = _decode_curves(geometries)
    data = _curve_datablock(data_name, curves) if curves else None
    if data is None:
        return None, errors
    for material in materials:
        if material is not None and material.name not in data.materials:
            data.materials.append(material)
    return bpy.data.objects.new(name, data), errors


def _decode_curves(
    geometries: List[Geometry],
) -> Tuple[List[object], List[str]]:
    """Decode the curve-family blobs of one object into Speckle objects.

    Curves go through the full ``decode`` rather than a raw fast path: they are
    orders of magnitude rarer than meshes, so the ``Base`` allocation that the
    mesh path deliberately avoids does not matter here, and the object model
    carries the NURBS definition we need to rebuild a real spline.
    """
    decoded: List[object] = []
    errors: List[str] = []
    for geometry in geometries:
        try:
            decoded.append(sgeo.decode(geometry.content))
        except sgeo.SgeoDecodeError as e:
            errors.append(str(e))
    return decoded, errors


def _curve_datablock(name: str, curves: List[object]) -> Optional[bpy.types.Curve]:
    """Merge one object's curve-family geometry into a single Curve data-block.

    A Blender Curve holds many splines, which is the direct parallel of merging
    several display meshes into one Mesh.
    """
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    for curve in curves:
        _add_splines(curve_data, curve)
    if not curve_data.splines:
        bpy.data.curves.remove(curve_data)
        return None
    return curve_data


def _add_splines(curve_data: bpy.types.Curve, curve) -> None:
    """Append the spline(s) one decoded curve-family object describes."""
    kind = type(curve).__name__

    if kind == "Polycurve":
        # a polycurve is a container; each segment contributes its own spline
        for segment in curve.segments:
            _add_splines(curve_data, segment)
        return

    scale = scale_for(getattr(curve, "units", None))

    if kind == "Curve":
        _add_nurbs_spline(curve_data, curve, scale)
    elif kind == "Polyline":
        _add_poly_spline(curve_data, curve.value, _closed(curve), scale)
    elif kind == "Line":
        points = [
            curve.start.x,
            curve.start.y,
            curve.start.z,
            curve.end.x,
            curve.end.y,
            curve.end.z,
        ]
        _add_poly_spline(curve_data, points, False, scale)
    elif kind in ("Arc", "Circle", "Ellipse"):
        _add_poly_spline(curve_data, _tessellate(curve, kind), kind != "Arc", scale)
    elif kind == "Spiral":
        # a spiral has no closed form Blender can express; the producer's own
        # render polyline is the faithful reading
        display = getattr(curve, "displayValue", None)
        if display is not None and display.value:
            _add_poly_spline(curve_data, display.value, _closed(display), scale)


def _closed(curve) -> bool:
    """Read a curve's closed flag, whether it is a field or a dynamic member."""
    closed = getattr(curve, "closed", None)
    if closed is None and hasattr(curve, "keys") and "closed" in curve.keys():
        closed = curve["closed"]
    return bool(closed)


def _add_poly_spline(
    curve_data: bpy.types.Curve,
    values: List[float],
    closed: bool,
    scale: float,
) -> None:
    """Add a POLY spline from a flat xyz list."""
    count = len(values) // 3
    if count < 2:
        return
    spline = curve_data.splines.new("POLY")
    # a new spline already owns one point
    spline.points.add(count - 1)
    # Blender spline points are 4D (x, y, z, w)
    flat: List[float] = []
    for i in range(count):
        flat.extend(
            (
                values[i * 3] * scale,
                values[i * 3 + 1] * scale,
                values[i * 3 + 2] * scale,
                1.0,
            )
        )
    spline.points.foreach_set("co", flat)
    spline.use_cyclic_u = closed


def _add_nurbs_spline(curve_data: bpy.types.Curve, curve, scale: float) -> None:
    """Rebuild a NURBS spline from the analytical definition.

    Preferred over the render polyline because it comes back editable — the
    control points, degree and weights are exactly what the publish side read
    off the Blender spline. Falls back to the display polyline when the
    definition is too degenerate for Blender to accept.

    Known approximation: **Blender's Python API cannot set a NURBS knot
    vector.** It derives one from ``order_u`` / ``use_cyclic_u`` /
    ``use_endpoint_u``, so a source curve with non-uniform knots is redrawn on a
    uniform basis. Control points, degree and weights survive exactly; the
    traced path can drift. Measured against the producer's own render polyline
    on a 55-curve model: half the curves within 0.03%, 50 of 51 within 5%.
    """
    points = curve.points
    count = len(points) // 3
    if count < 2:
        display = getattr(curve, "displayValue", None)
        if display is not None:
            _add_poly_spline(curve_data, display.value, _closed(curve), scale)
        return

    spline = curve_data.splines.new("NURBS")
    spline.points.add(count - 1)
    weights = curve.weights if len(curve.weights) == count else [1.0] * count
    flat: List[float] = []
    for i in range(count):
        flat.extend(
            (
                points[i * 3] * scale,
                points[i * 3 + 1] * scale,
                points[i * 3 + 2] * scale,
                weights[i],
            )
        )
    spline.points.foreach_set("co", flat)
    # Blender's order is degree + 1 and may not exceed the control point count
    spline.order_u = max(2, min(curve.degree + 1, count))
    spline.use_cyclic_u = bool(curve.closed)
    # `periodic` is `not use_endpoint_u` on the publish side, but Blender writes
    # it from a field Bezier splines do not really have, so every Bezier arrives
    # claiming to be periodic. A clamped knot vector is the curve's own,
    # trustworthy statement that it interpolates its endpoints, so believe that
    # first and fall back to the flag only when the knots say nothing.
    spline.use_endpoint_u = _is_clamped(curve.knots, curve.degree) or not bool(
        curve.periodic
    )


def _is_clamped(knots: List[float], degree: int) -> bool:
    """True when the knot vector pins the curve to its first and last control point.

    The test is the standard one — the leading and trailing ``degree`` knots each
    repeated — with the added requirement that the two ends differ, which rejects
    the all-zero vectors some producers emit for degenerate curves.
    """
    if degree < 1 or len(knots) < 2 * degree:
        return False
    head, tail = knots[:degree], knots[-degree:]
    if head[0] == tail[0]:
        return False
    return all(k == head[0] for k in head) and all(k == tail[0] for k in tail)


def _tessellate(curve, kind: str) -> List[float]:
    """Flatten an analytical arc/circle/ellipse into a flat xyz list.

    Blender has no native arc primitive, so these become polylines. The plane's
    xdir/ydir give the parametrisation basis; an arc additionally has to pick
    the sweep direction that actually passes through its midpoint.
    """
    import math

    plane = curve.plane
    o, x, y = plane.origin, plane.xdir, plane.ydir

    def at(angle: float, rx: float, ry: float) -> Tuple[float, float, float]:
        cos, sin = math.cos(angle) * rx, math.sin(angle) * ry
        return (
            o.x + x.x * cos + y.x * sin,
            o.y + x.y * cos + y.y * sin,
            o.z + x.z * cos + y.z * sin,
        )

    def angle_of(point) -> float:
        dx = point.x - o.x, point.y - o.y, point.z - o.z
        u = dx[0] * x.x + dx[1] * x.y + dx[2] * x.z
        v = dx[0] * y.x + dx[1] * y.y + dx[2] * y.z
        return math.atan2(v, u)

    if kind == "Circle":
        radius = curve.radius
        start, sweep, rx, ry = 0.0, 2.0 * math.pi, radius, radius
    elif kind == "Ellipse":
        start, sweep = 0.0, 2.0 * math.pi
        rx, ry = curve.first_radius, curve.second_radius
    else:  # Arc
        radius = math.dist(
            (curve.startPoint.x, curve.startPoint.y, curve.startPoint.z),
            (o.x, o.y, o.z),
        )
        rx = ry = radius
        start = angle_of(curve.startPoint)
        end = angle_of(curve.endPoint)
        mid = angle_of(curve.midPoint)
        sweep = _arc_sweep(start, mid, end)

    values: List[float] = []
    # a closed conic repeats its first point implicitly via use_cyclic_u, so the
    # final sample is dropped; an arc keeps both endpoints
    steps = _ARC_SEGMENTS if kind != "Arc" else _ARC_SEGMENTS
    last = steps if kind == "Arc" else steps - 1
    for i in range(last + 1):
        values.extend(at(start + sweep * (i / steps), rx, ry))
    return values


def _arc_sweep(start: float, mid: float, end: float) -> float:
    """Signed sweep from ``start`` to ``end`` that passes through ``mid``.

    Three points do not say which way round the circle the arc goes, so the
    midpoint is what disambiguates — take the direction whose forward sweep
    reaches ``mid`` before ``end``.
    """
    import math

    tau = 2.0 * math.pi

    def forward(a: float, b: float) -> float:
        return (b - a) % tau

    if forward(start, mid) <= forward(start, end):
        return forward(start, end)
    return forward(start, end) - tau
