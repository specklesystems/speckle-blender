import math
from typing import Union
from bpy_speckle.functions import get_scale_length, _report
import mathutils
import bpy, bmesh, bpy_types
from specklepy.objects.other import *
from specklepy.objects.geometry import *
from bpy.types import Object
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


def can_convert_to_native(speckle_object: Base) -> bool:
    if type(speckle_object) in CAN_CONVERT_TO_NATIVE:
        return True
    if getattr(
        speckle_object, "displayValue", getattr(speckle_object, "displayMesh", None)
    ):
        return True

    _report(f"Could not convert unsupported Speckle object: {speckle_object}")
    return False


def convert_to_native(speckle_object: Base, name: Optional[str] = None) -> Optional[Union[list, Object]]:
    speckle_type = type(speckle_object)
    speckle_name = (
        name
        or getattr(speckle_object, "name", None)
        or f"{speckle_object.speckle_type} -- {speckle_object.id}"
    )
    # convert unsupported types with display values
    if speckle_type not in CAN_CONVERT_TO_NATIVE:
        elements = getattr(speckle_object, "elements", []) or []
        display = getattr(
            speckle_object, "displayValue", getattr(speckle_object, "displayMesh", None)
        )
        if not elements and not display:
            _report(f"Could not convert unsupported Speckle object: {speckle_object}")
            return None
        if isinstance(display, list):
            elements.extend(display)
        else:
            elements.append(display)
        # TODO: depreciate the parent type
        # add parent type here so we can use it as a blender custom prop
        # not making it hidden, so it will get added on send as i think it might be helpful? can reconsider
        converted = []
        for item in elements:
            if not isinstance(item, Base):
                continue
            item.parent_speckle_type = speckle_object.speckle_type
            blender_object = convert_to_native(item)
            if isinstance(blender_object, list):
                converted.extend(blender_object)
            else:
                add_custom_properties(speckle_object, blender_object)
                converted.append(blender_object)
        return converted
        
    try:
        # convert breps
        if speckle_type is Brep:
            meshes = getattr(
                speckle_object, "displayValue", getattr(speckle_object, "displayMesh", iter([]))
            )
            if material := getattr(speckle_object, "renderMaterial", getattr(speckle_object, "@renderMaterial", None),):
                for mesh in meshes:
                    mesh["renderMaterial"] = material

            return [convert_to_native(mesh) for mesh in meshes]

        scale = 1.0
        if units := getattr(speckle_object, "units", None):
            scale = get_scale_length(units) / bpy.context.scene.unit_settings.scale_length
        # convert supported geometry
        if isinstance(speckle_object, Mesh):
            obj_data = mesh_to_native(speckle_object, name=speckle_name, scale=scale)
        elif speckle_type in SUPPORTED_CURVES:
            obj_data = icurve_to_native(speckle_object, name=speckle_name, scale=scale)
        elif isinstance(speckle_object, Transform):
            obj_data = transform_to_native(speckle_object, scale=scale)
        elif isinstance(speckle_object, BlockDefinition):
            obj_data = block_def_to_native(speckle_object, scale=scale)
        elif isinstance(speckle_object, BlockInstance): # speckle_type is BlockInstance:
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


def mesh_to_native(speckle_mesh: Mesh, name: str, scale=1.0) -> bpy.types.Mesh:

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

def line_to_native(speckle_curve: Line, blender_curve: bpy.types.Curve, scale: float) -> Optional[bpy.types.Spline]:
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


def polyline_to_native(scurve: Polyline, bcurve: bpy.types.Curve, scale: float) -> Optional[bpy.types.Spline]:
    if value := scurve.value:
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


def nurbs_to_native(scurve: Curve, bcurve: bpy.types.Curve, scale: float) -> Optional[bpy.types.Spline]:
    if points := scurve.points:
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


def arc_to_native(rcurve: Arc, bcurve: bpy.types.Curve, scale: float) -> Optional[bpy.types.Spline]:
    # TODO: improve Blender representation of arc

    plane = rcurve.plane
    if not plane:
        return None

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


def polycurve_to_native(scurve: Polycurve, bcurve: bpy.types.Curve, scale: float):
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


def icurve_to_native_spline(speckle_curve: Base, blender_curve: bpy.types.Curve, scale=1.0):
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


def icurve_to_native(speckle_curve: Base, name=None, scale=1.0) -> Optional[Curve]:
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


def transform_to_native(transform: Transform, scale=1.0) -> mathutils.Matrix:
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


def block_def_to_native(definition: BlockDefinition, scale=1.0) -> bpy.types.Collection:
    native_def = bpy.data.collections.get(definition.name)
    if native_def:
        return native_def

    native_def = bpy.data.collections.new(definition.name)
    native_def["applicationId"] = definition.applicationId
    for geo in definition.geometry:
        if b_obj := convert_to_native(geo):
            native_def.objects.link(
                b_obj
                if isinstance(b_obj, bpy_types.Object)
                else bpy.data.objects.new(b_obj.name, b_obj)
            )

    return native_def


def block_instance_to_native(instance: BlockInstance, scale=1.0) -> bpy.types.Object:
    """
    Convert BlockInstance to native
    """
    name = f"{getattr(instance, 'name', None) or instance.blockDefinition.name} -- {instance.id}"
    native_def = block_def_to_native(instance.blockDefinition, scale)

    native_instance = bpy.data.objects.new(name, None)
    add_custom_properties(instance, native_instance)
    native_instance["name"] = getattr(instance, 'name', None) or instance.blockDefinition.name
    # hide the instance axes so they don't clutter the viewport
    native_instance.empty_display_size = 0
    native_instance.instance_collection = native_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world = transform_to_native(instance.transform, scale)
    return native_instance
