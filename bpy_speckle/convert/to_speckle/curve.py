import bpy, bmesh, struct
from specklepy.objects.geometry import Curve, Interval, Box, Polyline
from bpy_speckle.convert.to_speckle.mesh import export_mesh

UNITS = "m"


def bezier_to_speckle(matrix, spline, scale, name=None):
    degree = 3
    closed = spline.use_cyclic_u

    points = []
    for i, bp in enumerate(spline.bezier_points):
        if i > 0:
            points.append(tuple(matrix @ bp.handle_left * scale))
        points.append(tuple(matrix @ bp.co * scale))
        if i < len(spline.bezier_points) - 1:
            points.append(tuple(matrix @ bp.handle_right * scale))

    if closed:
        points.append(tuple(matrix @ spline.bezier_points[-1].handle_right * scale))
        points.append(tuple(matrix @ spline.bezier_points[0].handle_left * scale))
        points.append(tuple(matrix @ spline.bezier_points[0].co * scale))

    num_points = len(points)

    knot_count = num_points + degree - 1
    knots = [0] * knot_count

    for i in range(1, len(knots)):
        knots[i] = i // 3

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Curve(
        name=name,
        degree=degree,
        closed=spline.use_cyclic_u,
        periodic=spline.use_cyclic_u,
        points=list(sum(points, ())),  # magic (flatten list of tuples)
        weights=[1] * num_points,
        knots=knots,
        rational=False,
        area=0,
        volume=0,
        length=length,
        domain=domain,
        units=UNITS,
        bbox=Box(area=0.0, volume=0.0),
    )


def nurbs_to_speckle(matrix, spline, scale, name=None):
    knots = makeknots(spline)
    # print("knots: {}".format(knots))
    points = [tuple(matrix @ pt.co.xyz * scale) for pt in spline.points]
    degree = spline.order_u - 1

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)

    return Curve(
        name=name,
        degree=degree,
        closed=spline.use_cyclic_u,
        periodic=spline.use_cyclic_u,
        points=list(sum(points, ())),  # magic (flatten list of tuples)
        weights=[pt.weight for pt in spline.points],
        knots=knots,
        rational=False,
        area=0,
        volume=0,
        length=length,
        domain=domain,
        units=UNITS,
        bbox=Box(area=0.0, volume=0.0),
    )


def poly_to_speckle(matrix, spline, scale, name=None):
    points = [tuple(matrix @ pt.co.xyz * scale) for pt in spline.points]

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Polyline(
        name=name,
        closed=spline.use_cyclic_u,
        value=list(sum(points, ())),  # magic (flatten list of tuples)
        length=length,
        domain=domain,
        bbox=Box(area=0.0, volume=0.0),
        area=0,
        units=UNITS,
    )


def export_curve(blender_object, data, scale=1.0):
    UNITS = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

    if blender_object.type != "CURVE":
        return None

    blender_object = blender_object.evaluated_get(bpy.context.view_layer.depsgraph)

    mat = blender_object.matrix_world

    curves = []

    if data.bevel_mode == "OBJECT" and data.bevel_object != None:
        mesh = export_mesh(blender_object, blender_object.to_mesh(), scale)
        curves.extend(mesh)

    for spline in data.splines:
        if spline.type == "BEZIER":
            curves.append(bezier_to_speckle(mat, spline, scale, blender_object.name))

        elif spline.type == "NURBS":
            curves.append(nurbs_to_speckle(mat, spline, scale, blender_object.name))

        elif spline.type == "POLY":
            curves.append(poly_to_speckle(mat, spline, scale, blender_object.name))

    return curves


def export_ngons_as_polylines(blender_object, data, scale=1.0):
    UNITS = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

    if blender_object.type != "MESH":
        return None

    mat = blender_object.matrix_world

    verts = data.vertices
    polylines = []
    for i, poly in enumerate(data.polygons):
        value = []
        for v in poly.vertices:
            value.extend(mat @ verts[v].co * scale)

        domain = Interval(start=0, end=1)
        poly = Polyline(
            name="{}_{}".format(blender_object.name, i),
            closed=True,
            value=value,  # magic (flatten list of tuples)
            length=0,
            domain=domain,
            bbox=Box(area=0.0, volume=0.0),
            area=0,
            units=UNITS,
        )

        polylines.append(poly)

    return polylines


"""
Python implementation of Blender's NURBS curve generation
from: https://blender.stackexchange.com/a/34276
"""


def macro_knotsu(nu):
    return nu.order_u + nu.point_count_u + (nu.order_u - 1 if nu.use_cyclic_u else 0)


def macro_segmentsu(nu):
    return nu.point_count_u if nu.use_cyclic_u else nu.point_count_u - 1


def makeknots(nu):
    knots = [0.0] * (4 + macro_knotsu(nu))
    flag = nu.use_endpoint_u + (nu.use_bezier_u << 1)
    if nu.use_cyclic_u:
        calcknots(knots, nu.point_count_u, nu.order_u, 0)
        makecyclicknots(knots, nu.point_count_u, nu.order_u)
    else:
        calcknots(knots, nu.point_count_u, nu.order_u, flag)
    return knots


def calcknots(knots, pnts, order, flag):
    pnts_order = pnts + order
    if flag == 1:
        k = 0.0
        for a in range(1, pnts_order + 1):
            knots[a - 1] = k
            if a >= order and a <= pnts:
                k += 1.0
    elif flag == 2:
        if order == 4:
            k = 0.34
            for a in range(pnts_order):
                knots[a] = math.floor(k)
                k += 1.0 / 3.0
        elif order == 3:
            k = 0.6
            for a in range(pnts_order):
                if a >= order and a <= pnts:
                    k += 0.5
                    knots[a] = math.floor(k)
    else:
        for a in range(pnts_order):
            knots[a] = a


def makecyclicknots(knots, pnts, order):
    order2 = order - 1

    if order > 2:
        b = pnts + order2
        for a in range(1, order2):
            if knots[b] != knots[b - a]:
                break

            if a == order2:
                knots[pnts + order - 2] += 1.0

    b = order
    c = pnts + order + order2
    for a in range(pnts + order2, c):
        knots[a] = knots[a - 1] + (knots[b] - knots[b - 1])
        b -= 1
