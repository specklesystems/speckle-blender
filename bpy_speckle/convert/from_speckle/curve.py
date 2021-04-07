import bpy, math
from bpy_speckle.util import find_key_case_insensitive
from mathutils import Vector, Quaternion
from speckle.objects.geometry import *

CONVERT = {}


def import_line(scurve, bcurve, scale):
    line = bcurve.splines.new("POLY")
    line.points.add(1)

    line.points[0].co = (
        float(scurve.start.x) * scale,
        float(scurve.start.y) * scale,
        float(scurve.start.z) * scale,
        1,
    )

    if scurve.end:

        line.points[1].co = (
            float(scurve.end.x) * scale,
            float(scurve.end.y) * scale,
            float(scurve.end.z) * scale,
            1,
        )

        return line


CONVERT[Line] = import_line


def import_polyline(scurve, bcurve, scale):

    # value = find_key_case_insensitive(scurve, "value")
    value = scurve.value

    if value:
        N = int(len(value) / 3)

        polyline = bcurve.splines.new("POLY")

        if hasattr(scurve, "closed"):
            polyline.use_cyclic_u = scurve.closed

        # if "closed" in scurve.keys():
        #    polyline.use_cyclic_u = scurve["closed"]

        polyline.points.add(N - 1)
        for i in range(N):
            polyline.points[i].co = (
                float(value[i * 3]) * scale,
                float(value[i * 3 + 1]) * scale,
                float(value[i * 3 + 2]) * scale,
                1,
            )

        return polyline


CONVERT[Polyline] = import_polyline


def import_nurbs_curve(scurve, bcurve, scale):

    # points = find_key_case_insensitive(scurve, "points")
    points = scurve.points

    if points:
        N = int(len(points) / 3)

        nurbs = bcurve.splines.new("NURBS")

        if hasattr(scurve, "closed"):
            nurbs.use_cyclic_u = scurve.closed != 0

        nurbs.points.add(N - 1)
        for i in range(N):
            nurbs.points[i].co = (
                float(points[i * 3]) * scale,
                float(points[i * 3 + 1]) * scale,
                float(points[i * 3 + 2]) * scale,
                1,
            )

        if len(scurve.weights == len(nurbs.points)):
            for i, w in enumerate(scurve.weights):
                nurbs.points[i].weight = w

        # TODO: anaylize curve knots to decide if use_endpoint_u or use_bezier_u should be enabled
        # nurbs.use_endpoint_u = True
        nurbs.order_u = scurve.degree + 1

        return nurbs


CONVERT[Curve] = import_nurbs_curve


def import_arc(rcurve, bcurve, scale):
    """
    Convert Arc object
    TODO: improve Blender representation of arc
    """
    plane = rcurve.plane
    if not plane:
        return

    origin = plane.origin
    normal = Vector(plane.normal.value)

    xaxis = plane.xdir
    yaxis = plane.ydir

    radius = rcurve.radius * scale
    startAngle = rcurve.startAngle
    endAngle = rcurve.endAngle

    startQuat = Quaternion(normal, startAngle)
    endQuat = Quaternion(normal, endAngle)

    """
    Get start and end vectors, centre point, angles, etc.
    """

    r1 = Vector(plane.xdir.value)
    r1.rotate(startQuat)

    r2 = Vector(plane.xdir.value)
    r2.rotate(endQuat)

    c = Vector(plane.origin.value) * scale

    spt = c + r1 * radius
    ept = c + r2 * radius

    angle = endAngle - startAngle

    t1 = normal.cross(r1)

    """
    Initialize arc data and calculate subdivisions
    """
    arc = bcurve.splines.new("NURBS")

    arc.use_cyclic_u = False

    Ndiv = max(int(math.floor(angle / 0.3)), 2)
    step = angle / float(Ndiv)
    stepQuat = Quaternion(normal, step)
    tan = math.tan(step / 2) * radius

    arc.points.add(Ndiv + 1)

    """
    Set start and end points
    """
    arc.points[0].co = (spt.x, spt.y, spt.z, 1)
    arc.points[Ndiv + 1].co = (ept.x, ept.y, ept.z, 1)

    """
    Set intermediate points
    """
    for i in range(Ndiv):
        t1 = normal.cross(r1)
        pt = c + r1 * radius + t1 * tan
        arc.points[i + 1].co = (pt.x, pt.y, pt.z, 1)
        r1.rotate(stepQuat)

    """
    Set curve settings
    """

    arc.use_endpoint_u = True
    arc.order_u = 3

    return arc


CONVERT[Arc] = import_arc


def import_null(speckle_object, bcurve, scale):
    """
    Handle unsupported types
    """
    print("Failed to convert type", speckle_object["type"])
    return None


def import_polycurve(scurve, bcurve, scale):
    """
    Convert Polycurve object
    """
    segments = scurve.segments

    curves = []

    for seg in segments:
        speckle_type = type(seg)

        if speckle_type in CONVERT.keys():
            # segcurve = SCHEMAS[speckle_type].parse_obj(seg)
            curves.append(CONVERT[speckle_type](seg, bcurve, scale))
        else:
            print("Unsupported curve type: {}".format(speckle_type))

    return curves


CONVERT[Polycurve] = import_polycurve


def import_curve(speckle_curve, scale, name=None):
    """
    Convert Curve object
    """
    if not name:
        name = speckle_curve.geometryHash or speckle_curve.id or "SpeckleCurve"

    if name in bpy.data.curves.keys():
        curve_data = bpy.data.curves[name]
    else:
        curve_data = bpy.data.curves.new(name, type="CURVE")

    curve_data.dimensions = "3D"
    curve_data.resolution_u = 12

    if type(speckle_curve) not in CONVERT.keys():
        print("Unsupported curve type: {}".format(speckle_curve.type))
        return None

    CONVERT[type(speckle_curve)](speckle_curve, curve_data, scale)

    return curve_data
