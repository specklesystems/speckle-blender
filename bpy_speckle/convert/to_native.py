import math
from typing import Iterable, Union, Collection
from bpy_speckle.convert.to_speckle import transform_to_speckle
from bpy_speckle.functions import get_scale_length, _report
import mathutils
import bpy, bmesh, bpy_types
from specklepy.objects.other import *
from specklepy.objects.geometry import *
from bpy.types import Object
from .util import (
    get_render_material,
    render_material_to_native,
    add_custom_properties,
    add_vertices,
    add_faces,
    add_colors,
    add_uv_coords,
)

SUPPORTED_CURVES = (Line, Polyline, Curve, Arc, Polycurve, Ellipse, Circle)

CAN_CONVERT_TO_NATIVE = (
    Mesh,
    *SUPPORTED_CURVES,
    transform_to_speckle,
    BlockDefinition,
    BlockInstance,
)


def can_convert_to_native(speckle_object: Base) -> bool:
    if type(speckle_object) in CAN_CONVERT_TO_NATIVE:
        return True

    for alias in DISPLAY_VALUE_PROPERTY_ALIASES:
        if getattr(speckle_object, alias, None):
            return True

    _report(f"Could not convert unsupported Speckle object: {speckle_object}")
    return False


def convert_to_native(speckle_object: Base) -> list[Object]:
    speckle_type = type(speckle_object)
    speckle_name = generate_object_name(speckle_object)
    try:
        scale = get_scale_factor(speckle_object)

        obj_data: Optional[Union[bpy.types.ID, bpy.types.Object, mathutils.Matrix]] = None
        converted: list[Object] = []

        # convert elements/breps
        if speckle_type not in CAN_CONVERT_TO_NATIVE:
            (obj_data, converted) = display_value_to_native(speckle_object, speckle_name, scale)

        # convert supported geometry
        elif isinstance(speckle_object, Mesh):
            obj_data = mesh_to_native(speckle_object, speckle_name, scale)
        elif speckle_type in SUPPORTED_CURVES:
            obj_data = icurve_to_native(speckle_object, speckle_name, scale)
        elif isinstance(speckle_object, Transform):
            obj_data = transform_to_native(speckle_object, scale)
        elif isinstance(speckle_object, BlockDefinition):
            obj_data = block_def_to_native(speckle_object)
        elif isinstance(speckle_object, BlockInstance):
            obj_data = block_instance_to_native(speckle_object, scale)
        else:
            _report(f"Unsupported type {speckle_type}")
            return []
    except Exception as ex:  # conversion error
        _report(f"Error converting {speckle_object} \n{ex}")
        return []

    if speckle_name in bpy.data.objects.keys():
        blender_object = bpy.data.objects[speckle_name]
        blender_object.data = (
            obj_data.data if isinstance(obj_data, Object) else obj_data
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
            if isinstance(obj_data, Object)
            else bpy.data.objects.new(speckle_name, obj_data)
        )

    blender_object.speckle.object_id = str(speckle_object.id)
    blender_object.speckle.enabled = True
    add_custom_properties(speckle_object, blender_object)

    for child in converted:
        child.parent = blender_object

    converted.append(blender_object)
    return converted





def generate_object_name(speckle_object: Base) -> str:
    prefix = (getattr(speckle_object, "name", None)
        or getattr(speckle_object, "Name", None)
        or speckle_object.speckle_type.rsplit(':')[-1])

    return f"{prefix} -- {speckle_object.id}"

def get_scale_factor(speckle_object: Base, fallback: float = 1.0) -> float:
    scale = fallback
    if units := getattr(speckle_object, "units", None):
        scale = get_scale_length(units) / bpy.context.scene.unit_settings.scale_length
    return scale


DISPLAY_VALUE_PROPERTY_ALIASES = ["displayValue", "@displayValue", "displayMesh", "@displayMesh", "elements", "@elements"]

def display_value_to_native(speckle_object: Base, name: str, scale: float) -> tuple[Optional[bpy.types.Mesh], list[bpy.types.Object]]:
    """
    Converts mesh displayValues as one mesh
    Converts non-mesh displayValues as child Objects
    """
    meshes: list[Mesh] = []
    elements: list[Base] = []

    #NOTE: raw Mesh elements will be treated like displayValues, which is not ideal, but no connector sends raw Mesh elements so its fine
    for alias in DISPLAY_VALUE_PROPERTY_ALIASES:
        display = getattr(speckle_object, alias, None)

        count = 0
        max_depth = 255
        def seperate(value: Any) -> None:
            nonlocal meshes, elements, count, max_depth

            if isinstance(value, Mesh):
                meshes.append(value)
            elif isinstance(value, Base):
                elements.append(value)
            elif isinstance(value, list):
                count += 1
                if(count > max_depth):
                    return
                for x in value:
                    seperate(x) 

        seperate(display)


    converted: list[Object] = []
    mesh = None

    if meshes:
        mesh = meshes_to_native(speckle_object, meshes, name, scale)

    # add parent type here so we can use it as a blender custom prop
    # not making it hidden, so it will get added on send as i think it might be helpful? can reconsider
    for item in elements:
        item.parent_speckle_type = speckle_object.speckle_type
        blender_object = convert_to_native(item)
        if isinstance(blender_object, list):
            converted.extend(blender_object)
        else:
            add_custom_properties(speckle_object, blender_object)
            converted.append(blender_object)

    if not elements and not meshes:
        _report(f"Unsupported type {speckle_object.speckle_type}")

    return (mesh, converted)


def mesh_to_native(speckle_mesh: Mesh, name: str, scale: float) -> bpy.types.Mesh:
    return meshes_to_native(speckle_mesh, [speckle_mesh], name, scale)

def meshes_to_native(element: Base, meshes: Collection[Mesh], name: str, scale: float) -> bpy.types.Mesh:
    if name in bpy.data.meshes.keys():
        blender_mesh = bpy.data.meshes[name]
    else:
        blender_mesh = bpy.data.meshes.new(name=name)

    fallback_material = get_render_material(element)

    bm = bmesh.new()

    # First pass, add vertex data
    for mesh in meshes:
        scale = get_scale_factor(mesh, scale)
        add_vertices(mesh, bm, scale)

    bm.verts.ensure_lookup_table()

    # Second pass, add face data
    offset = 0
    for i, mesh in enumerate(meshes):
        add_faces(mesh, bm, offset, i)

        render_material = get_render_material(mesh) or fallback_material
        if render_material is not None:
            native_material = render_material_to_native(render_material)
            blender_mesh.materials.append(native_material)

        offset += len(mesh.vertices) // 3

    bm.faces.ensure_lookup_table()
    bm.verts.index_update()

    # Third pass, add vertex instance data
    for mesh in meshes:
        add_colors(mesh, bm)
        add_uv_coords(mesh, bm)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(blender_mesh)
    bm.free()  

    return blender_mesh


def line_to_native(speckle_curve: Line, blender_curve: bpy.types.Curve, scale: float) -> list[bpy.types.Spline]:
    if not speckle_curve.end: return []

    line = blender_curve.splines.new("POLY")
    line.points.add(1)

    line.points[0].co = (
        float(speckle_curve.start.x) * scale,
        float(speckle_curve.start.y) * scale,
        float(speckle_curve.start.z) * scale,
        1,
    )

    line.points[1].co = (
        float(speckle_curve.end.x) * scale,
        float(speckle_curve.end.y) * scale,
        float(speckle_curve.end.z) * scale,
        1,
    )

    return [line]


def polyline_to_native(scurve: Polyline, bcurve: bpy.types.Curve, scale: float) -> list[bpy.types.Spline]:
    if not (value := scurve.value): return []
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

    return [polyline]
    


def nurbs_to_native(scurve: Curve, bcurve: bpy.types.Curve, scale: float) -> list[bpy.types.Spline]:
    if not (points := scurve.points): return []

    # Closed curves from rhino will have n + degree points. We ignore the extras
    num_points = len(points) // 3 - scurve.degree if (scurve.closed) else (
        len(points) // 3)   
    
    nurbs = bcurve.splines.new("NURBS")
    nurbs.use_cyclic_u = scurve.closed
    nurbs.use_endpoint_u = not scurve.periodic
    
    nurbs.points.add(num_points - 1)
    use_weights = len(scurve.weights) >= num_points
    for i in range(num_points):
        nurbs.points[i].co = (
            float(points[i * 3]) * scale,
            float(points[i * 3 + 1]) * scale,
            float(points[i * 3 + 2]) * scale,
            1,
        )
        
        nurbs.points[i].weight = scurve.weights[i] if use_weights else 1

    nurbs.order_u = scurve.degree + 1

    return [nurbs]


def arc_to_native(rcurve: Arc, bcurve: bpy.types.Curve, scale: float) -> Optional[bpy.types.Spline]:
    # TODO: improve Blender representation of arc - check autocad test stream

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


def polycurve_to_native(scurve: Polycurve, bcurve: bpy.types.Curve, scale: float) -> list[bpy.types.Spline]:
    """
    Convert Polycurve object
    """
    segments = scurve.segments

    curves = []

    for seg in segments:
        speckle_type = type(seg)

        if speckle_type in SUPPORTED_CURVES:
            curves.append(icurve_to_native_spline(seg, bcurve, scale))
        else:
            _report(f"Unsupported curve type: {speckle_type}")

    return curves

def circle_to_native(circle: Circle, bcurve: bpy.types.Curve, units_scale: float) -> list[bpy.types.Spline]:
    #HACK: not the cleanest way
    circle["firstRadius"] = circle.radius
    circle["secondRadius"] = circle.radius
    return ellipse_to_native(circle, bcurve, units_scale) # type: ignore
 
def ellipse_to_native(ellipse: Ellipse, bcurve: bpy.types.Curve, units_scale: float) -> list[bpy.types.Spline]:
    plane = ellipse.plane

    radX = ellipse.firstRadius * units_scale
    radY = ellipse.secondRadius * units_scale

    D = 2 * 0.27606262

    right_handles = [
        (+radX,     +radY * D,  0.0),
        (-radX * D, +radY,      0.0),
        (-radX,     -radY * D,  0.0),
        (+radX * D, -radY,      0.0),
    ]

    left_handles = [
        (+radX,     -radY * D,  0.0),
        (+radX * D, +radY,      0.0),
        (-radX,     +radY * D,  0.0),
        (-radX * D, -radY,      0.0),
    ]

    points = [
        (+radX, 0.0,   0.0),
        (0.0,   +radY, 0.0),
        (-radX, 0.0,   0.0),
        (0.0,   -radY, 0.0),
    ]
    transform = plane_to_native_transform(plane, units_scale)

    spline = bcurve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)

    for i in range(len(points)):
        spline.bezier_points[i].co = transform @ mathutils.Vector(points[i])
        spline.bezier_points[i].handle_left = transform @ mathutils.Vector(left_handles[i])
        spline.bezier_points[i].handle_right = transform @ mathutils.Vector(right_handles[i])

    spline.use_cyclic_u = True
    
    #TODO support trims?
    return [spline]


def icurve_to_native_spline(speckle_curve: Base, blender_curve: bpy.types.Curve, scale: float) -> list[bpy.types.Spline]:
    # polycurves
    if isinstance(speckle_curve, Polycurve):
        return polycurve_to_native(speckle_curve, blender_curve, scale)

    # single curves
    if isinstance(speckle_curve, Line):
        spline = line_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Curve):
        spline = nurbs_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve,Polyline):
        spline = polyline_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Arc):
        spline =  arc_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Ellipse):
        spline =  ellipse_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Circle):
        spline =  circle_to_native(speckle_curve, blender_curve, scale)
    else:
        raise TypeError(f"{speckle_curve} is not a supported curve type. Supported types: {SUPPORTED_CURVES}")

    return [spline] if spline is not None else [] 


def icurve_to_native(speckle_curve: Base, name: str, scale: float) -> Optional[bpy.types.Curve]:
    curve_type = type(speckle_curve)
    if curve_type not in SUPPORTED_CURVES:
        _report(f"Unsupported curve type: {curve_type}")
        return None
    blender_curve = (
        bpy.data.curves[name]
        if name in bpy.data.curves.keys()
        else bpy.data.curves.new(name, type="CURVE")
    )
    blender_curve.dimensions = "3D"
    blender_curve.resolution_u = 12

    icurve_to_native_spline(speckle_curve, blender_curve, scale)

    return blender_curve


def transform_to_native(transform: Transform, scale: float) -> mathutils.Matrix:
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

def plane_to_native_transform(plane: Plane, fallback_scale:float = 1) -> mathutils.Matrix:
    scale_factor = get_scale_factor(plane, fallback_scale)
    tx = (plane.origin.x * scale_factor)
    ty = (plane.origin.y * scale_factor)
    tz = (plane.origin.z * scale_factor)

    return mathutils.Matrix((
        (plane.xdir.x,  plane.xdir.y,  plane.xdir.z , 0),
        (plane.ydir.x,  plane.ydir.y,  plane.ydir.z , 0),
        (plane.normal.x,  plane.normal.y,  plane.normal.z , 0),
        (tx, ty, tz, 1)
    )).transposed()

def block_def_to_native(definition: BlockDefinition) -> bpy.types.Collection:
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


def block_instance_to_native(instance: BlockInstance, scale: float) -> bpy.types.Object:
    """
    Convert BlockInstance to native
    """
    name = f"{getattr(instance, 'name', None) or instance.blockDefinition.name} -- {instance.id}"
    native_def = block_def_to_native(instance.blockDefinition)

    native_instance = bpy.data.objects.new(name, None)
    add_custom_properties(instance, native_instance)
    native_instance["name"] = getattr(instance, 'name', None) or instance.blockDefinition.name
    # hide the instance axes so they don't clutter the viewport
    native_instance.empty_display_size = 0
    native_instance.instance_collection = native_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world = transform_to_native(instance.transform, scale)
    return native_instance
