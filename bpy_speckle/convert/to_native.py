import math
from bpy_speckle.functions import get_scale_length, _report
import mathutils
import bpy, bmesh, bpy_types
from specklepy.objects.other import *
from specklepy.objects.geometry import *
from .util import (
    add_blender_material,
    add_custom_properties,
    add_vertices,
    add_faces,
    add_colors,
    add_uv_coords,
)

SUPPORTED_CURVES = (Line, Polyline, Curve, Arc, Polycurve)

CAN_CONVERT_TO_NATIVE = (
    Mesh,
    Brep,
    *SUPPORTED_CURVES,
    Transform,
    BlockDefinition,
    BlockInstance,
)


def can_convert_to_native(speckle_object):
    if type(speckle_object) in CAN_CONVERT_TO_NATIVE:
        return True
    display = getattr(
        speckle_object, "displayMesh", getattr(speckle_object, "displayValue", None)
    )
    if display:
        return True

    _report(f"Could not convert unsupported Speckle object: {speckle_object}")
    return False


def convert_to_native(speckle_object, name=None):
    speckle_type = type(speckle_object)
    speckle_name = (
        name
        or getattr(speckle_object, "name", None)
        or speckle_object.speckle_type + f" -- {speckle_object.id}"
    )
    if speckle_type not in CAN_CONVERT_TO_NATIVE:
        display = getattr(
            speckle_object, "displayMesh", getattr(speckle_object, "displayValue", None)
        )
        if not display:
            _report(f"Could not convert unsupported Speckle object: {speckle_object}")
            return
        # add parent type here so we can use it as a blender custom prop
        # not making it hidden, so it will get added on send as i think it might be helpful? can reconsider
        if isinstance(display, list):
            for item in display:
                item.parent_speckle_type = speckle_object.speckle_type
                convert_to_native(item)
        else:
            display.parent_speckle_type = speckle_object.speckle_type
            return convert_to_native(display, speckle_name)

    units = getattr(speckle_object, "units", None)
    if units:
        scale = get_scale_length(units) / bpy.context.scene.unit_settings.scale_length

    try:
        if speckle_type is Mesh:
            obj_data = mesh_to_native(speckle_object, name=speckle_name, scale=scale)
        elif speckle_type is Brep:
            obj_data = brep_to_native(speckle_object, name=speckle_name, scale=scale)
        elif speckle_type in SUPPORTED_CURVES:
            obj_data = icurve_to_native(speckle_object, name=speckle_name, scale=scale)
        elif speckle_type is Transform:
            obj_data = transform_to_native(speckle_object, scale=scale)
        elif speckle_type is BlockDefinition:
            obj_data = block_def_to_native(speckle_object, scale=scale)
        elif speckle_type is BlockInstance:
            obj_data = block_instance_to_native(speckle_object, scale=scale)
        else:
            _report(f"Unsupported type {speckle_type}")
            return None
    except Exception as ex:  # conversion error
        _report(f"Error converting {speckle_object} \n{ex}")
        return None

    if speckle_name in bpy.data.objects.keys():
        blender_object = bpy.data.objects[speckle_name]
        blender_object.data = (
            obj_data.data if isinstance(obj_data, bpy_types.Object) else obj_data
        )
        blender_object.matrix_world = (
            blender_object.matrix_world
            if speckle_type is BlockInstance
            else mathutils.Matrix()
        )
        if hasattr(obj_data, "materials"):
            blender_object.data.materials.clear()
    else:
        blender_object = (
            obj_data
            if isinstance(obj_data, bpy_types.Object)
            else bpy.data.objects.new(speckle_name, obj_data)
        )

    blender_object.speckle.object_id = str(speckle_object.id)
    blender_object.speckle.enabled = True
    add_custom_properties(speckle_object, blender_object)
    add_blender_material(speckle_object, blender_object)

    return blender_object


def brep_to_native(speckle_brep, name, scale=1.0):
    display = getattr(
        speckle_brep, "displayMesh", getattr(speckle_brep, "displayValue", None)
    )
    return mesh_to_native(display, name, scale) if display else None


def mesh_to_native(speckle_mesh, name, scale=1.0):

    if name in bpy.data.meshes.keys():
        blender_mesh = bpy.data.meshes[name]
    else:
        blender_mesh = bpy.data.meshes.new(name=name)

    bm = bmesh.new()

    add_vertices(speckle_mesh, bm, scale)
    add_faces(speckle_mesh, bm)
    add_colors(speckle_mesh, bm)
    add_uv_coords(speckle_mesh, bm)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(blender_mesh)
    bm.free()

    return blender_mesh


def line_to_native(speckle_curve, blender_curve, scale):
    line = blender_curve.splines.new("POLY")
    line.points.add(1)

    line.points[0].co = (
        float(speckle_curve.start.x) * scale,
        float(speckle_curve.start.y) * scale,
        float(speckle_curve.start.z) * scale,
        1,
    )

    if speckle_curve.end:

        line.points[1].co = (
            float(speckle_curve.end.x) * scale,
            float(speckle_curve.end.y) * scale,
            float(speckle_curve.end.z) * scale,
            1,
        )

        return line


def polyline_to_native(scurve, bcurve, scale):

    # value = find_key_case_insensitive(scurve, "value")
    value = scurve.value

    if value:
        N = len(value) // 3

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


def nurbs_to_native(scurve, bcurve, scale):

    # points = find_key_case_insensitive(scurve, "points")
    points = scurve.points

    if points:
        N = len(points) // 3

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

        if len(scurve.weights) == len(nurbs.points):
            for i, w in enumerate(scurve.weights):
                nurbs.points[i].weight = w

        # TODO: anaylize curve knots to decide if use_endpoint_u or use_bezier_u should be enabled
        # nurbs.use_endpoint_u = True
        nurbs.order_u = scurve.degree + 1

        return nurbs


def arc_to_native(rcurve, bcurve, scale):
    # TODO: improve Blender representation of arc

    plane = rcurve.plane
    if not plane:
        return

    normal = mathutils.Vector([plane.normal.x, plane.normal.y, plane.normal.z])

    radius = rcurve.radius * scale
    startAngle = rcurve.startAngle
    endAngle = rcurve.endAngle

    startQuat = mathutils.Quaternion(normal, startAngle)
    endQuat = mathutils.Quaternion(normal, endAngle)

    # Get start and end vectors, centre point, angles, etc.
    r1 = mathutils.Vector([plane.xdir.x, plane.xdir.y, plane.xdir.z])
    r1.rotate(startQuat)

    r2 = mathutils.Vector([plane.xdir.x, plane.xdir.y, plane.xdir.z])
    r2.rotate(endQuat)

    c = mathutils.Vector([plane.origin.x, plane.origin.y, plane.origin.z]) * scale

    spt = c + r1 * radius
    ept = c + r2 * radius

    angle = endAngle - startAngle

    t1 = normal.cross(r1)

    # Initialize arc data and calculate subdivisions
    arc = bcurve.splines.new("NURBS")

    arc.use_cyclic_u = False

    Ndiv = max(int(math.floor(angle / 0.3)), 2)
    step = angle / float(Ndiv)
    stepQuat = mathutils.Quaternion(normal, step)
    tan = math.tan(step / 2) * radius

    arc.points.add(Ndiv + 1)

    # Set start and end points
    arc.points[0].co = (spt.x, spt.y, spt.z, 1)
    arc.points[Ndiv + 1].co = (ept.x, ept.y, ept.z, 1)

    # Set intermediate points
    for i in range(Ndiv):
        t1 = normal.cross(r1)
        pt = c + r1 * radius + t1 * tan
        arc.points[i + 1].co = (pt.x, pt.y, pt.z, 1)
        r1.rotate(stepQuat)

    # Set curve settings
    arc.use_endpoint_u = True
    arc.order_u = 3

    return arc


def polycurve_to_native(scurve, bcurve, scale):
    """
    Convert Polycurve object
    """
    segments = scurve.segments

    curves = []

    for seg in segments:
        speckle_type = type(seg)

        if speckle_type in SUPPORTED_CURVES:
            curves.append(icurve_to_native_spline(seg, bcurve, scale=scale))
        else:
            _report(f"Unsupported curve type: {speckle_type}")

    return curves


def icurve_to_native_spline(speckle_curve, blender_curve, scale=1.0):
    curve_type = type(speckle_curve)
    if curve_type is Line:
        return line_to_native(speckle_curve, blender_curve, scale)
    if curve_type is Polyline:
        return polyline_to_native(speckle_curve, blender_curve, scale)
    if curve_type is Curve:
        return nurbs_to_native(speckle_curve, blender_curve, scale)
    if curve_type is Polycurve:
        return polycurve_to_native(speckle_curve, blender_curve, scale)
    if curve_type is Arc:
        return arc_to_native(speckle_curve, blender_curve, scale)


def icurve_to_native(speckle_curve, name=None, scale=1.0):
    curve_type = type(speckle_curve)
    if curve_type not in SUPPORTED_CURVES:
        _report(f"Unsupported curve type: {curve_type}")
        return None
    name = name or f"{curve_type} -- {speckle_curve.id}"
    blender_curve = (
        bpy.data.curves[name]
        if name in bpy.data.curves.keys()
        else bpy.data.curves.new(name, type="CURVE")
    )
    blender_curve.dimensions = "3D"
    blender_curve.resolution_u = 12

    icurve_to_native_spline(speckle_curve, blender_curve, scale)

    return blender_curve


def transform_to_native(transform: Transform, scale=1.0):
    mat = mathutils.Matrix(
        [
            transform.value[:4],
            transform.value[4:8],
            transform.value[8:12],
            transform.value[12:16],
        ]
    )
    # scale the translation
    for i in range(3):
        mat[i][3] *= scale
    return mat


def block_def_to_native(definition: BlockDefinition, scale=1.0):
    _report(f">>> creating block definition for {definition.name} ({definition.id})")
    native_def = bpy.data.collections.get(definition.name)
    if native_def:
        return native_def

    native_def = bpy.data.collections.new(definition.name)
    native_def["applicationId"] = definition.applicationId
    for geo in definition.geometry:
        b_obj = convert_to_native(geo)
        if b_obj:
            native_def.objects.link(
                b_obj
                if isinstance(b_obj, bpy_types.Object)
                else bpy.data.objects.new(b_obj.name, b_obj)
            )

    return native_def


def block_instance_to_native(instance: BlockInstance, scale=1.0):
    """
    Convert BlockInstance to native
    """
    _report(f">>> converting block instance {instance.id}")

    name = f"{getattr(instance, 'name', None) or instance.blockDefinition.name} -- {instance.id}"
    native_def = block_def_to_native(instance.blockDefinition, scale)

    native_instance = bpy.data.objects.new(name, None)
    # hide the instance axes so they don't clutter the viewport
    native_instance.empty_display_size = 0
    native_instance.instance_collection = native_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world = transform_to_native(instance.transform, scale)
    return native_instance
