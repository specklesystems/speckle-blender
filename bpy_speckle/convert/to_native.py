import math
from typing import Tuple, Union, Collection
from bpy_speckle.functions import get_scale_length, _report
from mathutils import (
    Matrix as MMatrix,
    Vector as MVector,
    Quaternion as MQuaternion,
)
import bpy, bmesh
from specklepy.objects.other import (
    Instance,
    Transform,
    BlockDefinition,
)
from specklepy.objects.geometry import *
from bpy.types import Object
from .util import (
    get_render_material,
    link_object_to_collection_nested,
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
    Instance,
)


def _has_native_convesion(speckle_object: Base) -> bool: 
    return any(isinstance(speckle_object, t) for t in CAN_CONVERT_TO_NATIVE) or "View" in speckle_object.speckle_type #hack

def _has_fallback_conversion(speckle_object: Base) -> bool: 
    return any(getattr(speckle_object, alias, None) for alias in DISPLAY_VALUE_PROPERTY_ALIASES)

def can_convert_to_native(speckle_object: Base) -> bool:

    if(_has_native_convesion(speckle_object) or _has_fallback_conversion(speckle_object)):
        return True

    _report(f"Could not convert unsupported Speckle object: {speckle_object}")
    return False

def create_new_object(obj_data: Optional[bpy.types.ID], desired_name: str, counter: int = 0) -> bpy.types.Object:
    """
    Creates a new blender object with a unique name,
    if the desired_name is already taken
    we'll append a number, with the format .xxx to the desired_name to ensure the name is unique.
    """
    name = desired_name if counter == 0 else f"{desired_name[:OBJECT_NAME_MAX_LENGTH - 4]}.{counter:03d}"  # format counter as name.xxx, truncate to ensure we don't exceed the object name max length

    #TODO: This is very slow, and gets slower the more objects you receive with the same name...
    # We could use a binary/galloping search, and/or cache the name -> index within a receive.
    if name in bpy.data.objects.keys(): 
        #Object already exists, increment counter and try again!
        return create_new_object(obj_data, desired_name, counter + 1)

    blender_object = bpy.data.objects.new(name, obj_data)
    return blender_object

convert_instances_as: str #HACK: This is hacky, we need a better way to pass settings down to the converter
def set_convert_instances_as(value: str):
    global convert_instances_as
    convert_instances_as = value
    
def convert_to_native(speckle_object: Base) -> list[Object]:

    speckle_type = type(speckle_object)
    try:
        object_name = _generate_object_name(speckle_object)
        scale = get_scale_factor(speckle_object)

        obj_data: Optional[Union[bpy.types.ID, bpy.types.Object]] = None
        converted: list[Object] = []

        # convert elements/breps
        if not _has_native_convesion(speckle_object):
            (obj_data, converted) = element_to_native(speckle_object, object_name, scale)
            if not obj_data and not converted:
                _report(f"Unsupported type {speckle_object.speckle_type}")

        # convert supported geometry
        elif isinstance(speckle_object, Mesh):
            obj_data = mesh_to_native(speckle_object, object_name, scale)
        elif speckle_type in SUPPORTED_CURVES:
            obj_data = icurve_to_native(speckle_object, object_name, scale)
        elif "View" in speckle_object.speckle_type:
            obj_data = view_to_native(speckle_object, object_name, scale)
        elif isinstance(speckle_object, Instance):
            if convert_instances_as == "linked_duplicates":
                (obj_data, converted) = instance_to_native_object(speckle_object, scale)
            elif convert_instances_as != "collection_instance":
                obj_data = instance_to_native_collection_instance(speckle_object, scale)
            else:
                _report(f"convert_instances_as = '{convert_instances_as}' is not implemented, Instances will be converted as collection instances!")
                obj_data = instance_to_native_collection_instance(speckle_object, scale)

        else:
            _report(f"Unsupported type {speckle_type}")
            return []
    except Exception as ex:  # conversion error
        _report(f"Error converting {speckle_object} \n{ex}")
        return []


    blender_object = obj_data if isinstance(obj_data, Object) else create_new_object(obj_data, object_name)
    
    blender_object.speckle.object_id = str(speckle_object.id)
    blender_object.speckle.enabled = True
    add_custom_properties(speckle_object, blender_object)

    for child in converted:
        child.parent = blender_object

    converted.append(blender_object)
    _report(f"Successfully converted {object_name} as {blender_object.type}")
    return converted


DISPLAY_VALUE_PROPERTY_ALIASES = ["displayValue", "@displayValue", "displayMesh", "@displayMesh", "elements", "@elements"]

def element_to_native(speckle_object: Base, name: str, scale: float, combineMeshes: bool = True) -> tuple[Optional[bpy.types.Mesh], list[bpy.types.Object]]:
    """
    Converts a given speckle_object by converting displayValue properties (elements treated the same as displayValues)

    if combineMeshes == True
        Converts mesh displayValues as one mesh
        Converts non-mesh displayValues as child Objects
    if combineMeshes == False
        Converts all displayValues as child objects (first item of the returned tuple will be None)
    """
    meshes: list[Mesh] = []
    elements: list[Base] = []

    #NOTE: raw Mesh elements will be treated like displayValues, which is not ideal, but no connector sends raw Mesh elements so it's fine
    for alias in DISPLAY_VALUE_PROPERTY_ALIASES:
        display = getattr(speckle_object, alias, None)

        count = 0
        MAX_DEPTH = 255 # some large value, to prevent infinite reccursion
        def seperate(value: Any) -> bool:
            nonlocal meshes, elements, count, MAX_DEPTH

            if combineMeshes and isinstance(value, Mesh):
                meshes.append(value)
            elif isinstance(value, Base):
                elements.append(value)
            elif isinstance(value, list):
                count += 1
                if(count > MAX_DEPTH):
                    return True
                for x in value:
                    seperate(x) 

            return False

        did_halt = seperate(display)

        if did_halt:
            _report(f"Traversal of {speckle_object.speckle_type} {speckle_object.id} halted after traversal depth exceeds MAX_DEPTH={MAX_DEPTH}. Are there circular references object structure?")


    converted: list[Object] = []
    mesh = None

    if meshes:
        mesh = meshes_to_native(speckle_object, meshes, name, scale)

    for item in elements:
        # add parent type here so we can use it as a blender custom prop
        # not making it hidden, so it will get added on send as i think it might be helpful? can reconsider
        item.parent_speckle_type = speckle_object.speckle_type #TODO: consider if this is still useful, as we now properly structure object parenting
        blender_object = convert_to_native(item)
        if isinstance(blender_object, list):
            converted.extend(blender_object)
        else:
            add_custom_properties(speckle_object, blender_object)
            converted.append(blender_object)

    return (mesh, converted)



def view_to_native(speckle_view, name: str, scale: float) -> bpy.types.Object:
    native_cam: bpy.types.Camera
    if name in bpy.data.cameras.keys():
         native_cam = bpy.data.cameras[name]
    else:
        native_cam = bpy.data.cameras.new(name=name)
        native_cam.lens = 18 # 90° horizontal fov

    cam_obj = create_new_object(native_cam, name)

    scale_factor = get_scale_factor(speckle_view, scale)
    tx = (speckle_view.origin.x * scale_factor)
    ty = (speckle_view.origin.y * scale_factor)
    tz = (speckle_view.origin.z * scale_factor)

    forward = MVector((speckle_view.forwardDirection.x, speckle_view.forwardDirection.y, speckle_view.forwardDirection.z))
    up = MVector((speckle_view.upDirection.x, speckle_view.upDirection.y, speckle_view.upDirection.z))
    right = forward.cross(up).normalized()

    cam_obj.matrix_world = MMatrix((
        (right.x,  up.x,  -forward.x, tx),
        (right.y,  up.y,  -forward.y, ty),
        (right.z,  up.z,  -forward.z, tz),
        (0,          0,     0,       1 )
    ))
    return cam_obj

def mesh_to_native(speckle_mesh: Mesh, name: str, scale: float) -> bpy.types.Mesh:
    return meshes_to_native(speckle_mesh, [speckle_mesh], name, scale)

def meshes_to_native(element: Base, meshes: Collection[Mesh], name: str, scale: float) -> bpy.types.Mesh:
    if name in bpy.data.meshes.keys():
        return bpy.data.meshes[name]

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


"""
Curves
"""

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

    normal = MVector([plane.normal.x, plane.normal.y, plane.normal.z])

    radius = rcurve.radius * scale
    startAngle = rcurve.startAngle
    endAngle = rcurve.endAngle

    startQuat = MQuaternion(normal, startAngle)
    endQuat = MQuaternion(normal, endAngle)

    # Get start and end vectors, centre point, angles, etc.
    r1 = MVector([plane.xdir.x, plane.xdir.y, plane.xdir.z])
    r1.rotate(startQuat)

    r2 = MVector([plane.xdir.x, plane.xdir.y, plane.xdir.z])
    r2.rotate(endQuat)

    c = MVector([plane.origin.x, plane.origin.y, plane.origin.z]) * scale

    spt = c + r1 * radius
    ept = c + r2 * radius

    angle = endAngle - startAngle

    t1 = normal.cross(r1)

    # Initialize arc data and calculate subdivisions
    arc = bcurve.splines.new("NURBS")

    arc.use_cyclic_u = False

    Ndiv = max(int(math.floor(angle / 0.3)), 2)
    step = angle / float(Ndiv)
    stepQuat = MQuaternion(normal, step)
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
 
def ellipse_to_native(ellipse: Union[Ellipse, Circle], bcurve: bpy.types.Curve, units_scale: float) -> list[bpy.types.Spline]:

    radX: float
    radY: float
    if isinstance(ellipse, Ellipse):
        radX = ellipse.firstRadius * units_scale
        radY = ellipse.secondRadius * units_scale
    else:
        radX = ellipse.radius * units_scale
        radY = ellipse.radius * units_scale

    
    D = 0.5522847498307936 # (4/3)*tan(pi/8)

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
    transform = plane_to_native_transform(ellipse.plane, units_scale)

    spline = bcurve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)

    for i in range(len(points)):
        spline.bezier_points[i].co = transform @ MVector(points[i])
        spline.bezier_points[i].handle_left = transform @ MVector(left_handles[i])
        spline.bezier_points[i].handle_right = transform @ MVector(right_handles[i])

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
    elif isinstance(speckle_curve, Polyline):
        spline = polyline_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Arc):
        spline =  arc_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Ellipse) or isinstance(speckle_curve, Circle):
        spline =  ellipse_to_native(speckle_curve, blender_curve, scale)
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
    blender_curve.resolution_u = 12 #TODO: We could maybe decern the resolution from the ployline displayValue

    icurve_to_native_spline(speckle_curve, blender_curve, scale)

    return blender_curve


"""
Transforms and Intances
"""

def transform_to_native(transform: Transform, scale: float) -> MMatrix:
    mat = MMatrix(
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

def plane_to_native_transform(plane: Plane, fallback_scale:float = 1) -> MMatrix:
    scale_factor = get_scale_factor(plane, fallback_scale)
    tx = (plane.origin.x * scale_factor)
    ty = (plane.origin.y * scale_factor)
    tz = (plane.origin.z * scale_factor)


    return MMatrix((
        (plane.xdir.x,  plane.ydir.x,  plane.normal.x, tx),
        (plane.xdir.y,  plane.ydir.y,  plane.normal.y, ty),
        (plane.xdir.z,  plane.ydir.z,  plane.normal.z, tz),
        (0,             0,             0,              1 )
    ))


"""
Instances / Blocks
"""

def _get_instance_name(instance: Instance) -> str:
    name_prefix = _get_friendly_object_name(instance) or _get_friendly_object_name(instance.definition) or _simplified_speckle_type(instance.speckle_type)
    return f"{name_prefix}{OBJECT_NAME_SEPERATOR}{instance.id}"


def instance_to_native_object(instance: Instance, scale: float) -> Tuple[bpy.types.Object, List[bpy.types.Object]]:
    """
    Converts Instance to a unique object with (potentially) shared data (linked duplicate)
    """
    if not instance.definition: raise Exception(f"Instance is missing a definition")
    if not instance.transform: raise Exception(f"Instance is missing a transform")

    name = _get_instance_name(instance)
    definition = instance.definition

    native_instance: Object
    native_elements: List[Object] = []
    elements_on_instance: List[Object] = []

    if isinstance(definition, BlockDefinition): #NOTE: We have to handle BlockDefinitions specially here, since they don't follow normal traversal rules
        native_instance = create_new_object(None, name) #Instance will be empty
        native_instance.empty_display_size = 0
        for geo in definition.geometry:
            native_elements.append(convert_to_native(geo)[-1])
    else:
        native_instance = convert_to_native(instance.definition)[-1] # Convert assuming that definition is convertable

    instance_transform = transform_to_native(instance.transform, scale)
    instance_transform_inverted = instance_transform.inverted()
    native_instance.matrix_world = instance_transform
    
    (_, elements_on_instance) = element_to_native(instance, name, scale)
    for c in elements_on_instance:
        c.matrix_world = instance_transform_inverted @ c.matrix_world #Undo the instance transform on elements

    native_elements.extend(elements_on_instance)
    
    return (native_instance, native_elements) #TODO: need to double check that all child objects have custom props attached correctly

def instance_to_native_collection_instance(instance: Instance, scale: float) -> bpy.types.Object:
    """
    Convert an Instance as a transformed Object with the `instance_collection` property
    set to be the `instance.Definition` converted as a collection

    The definition collection won't be linked to the current scene
    Any Elements on the instance object will also be converted (and spacially transformed)
    """
    if not instance.definition: raise Exception(f"Instance is missing a definition")
    if not instance.transform: raise Exception(f"Instance is missing a transform")

    name = _get_instance_name(instance)

    # Get/Convert definition collection
    collection_def = _instance_definition_to_native(instance.definition)

    # Convert elements as children of collection instance object
    (_, elements) = element_to_native(instance, name, scale, False)

    instance_transform = transform_to_native(instance.transform, scale)
    instance_transform_inverted = instance_transform.inverted()

    native_instance = bpy.data.objects.new(name, None)

    #add_custom_properties(instance, native_instance)
    # hide the instance axes so they don't clutter the viewport
    native_instance.empty_display_size = 0
    native_instance.instance_collection = collection_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world =instance_transform

    for c in elements:
        c.matrix_world = instance_transform_inverted @ c.matrix_world #Undo the instance transform on elements
        c.parent = native_instance #TODO: need to double check that all child objects have custom props attached correctly

    return native_instance 

def _instance_definition_to_native(definition: Union[Base, BlockDefinition]) -> bpy.types.Collection:
    """
    Converts a geometry carrying Base as a collection (does not link it to the scene)
    """
    name = _generate_object_name(definition)
    native_def = bpy.data.collections.get(name)
    if native_def:
        return native_def

    native_def = bpy.data.collections.new(name)
    native_def["applicationId"] = definition.applicationId

    #TODO could maybe replace BlockDefinition awareness with a single traverse member call
    geometry = definition.geometry if isinstance(definition, BlockDefinition) else [definition]

    for geo in geometry:
        if not geo: continue
        converted = convert_to_native(geo)[-1] #NOTE: we assume the last item is the root converted item
        link_object_to_collection_nested(converted, native_def)


    return native_def


"""
Object Naming
"""

def _get_friendly_object_name(speckle_object: Base) -> Optional[str]:
    return (getattr(speckle_object, "name", None)
        or getattr(speckle_object, "Name", None)
        or getattr(speckle_object, "family", None)
        )


# Blender object names must not exceed 62 characters
# We need to ensure the complete ID is included in the name (to prevent identity collisions)
# So we if the name is too long, we need to truncate
OBJECT_NAME_MAX_LENGTH = 62
SPECKLE_ID_LENGTH = 32
OBJECT_NAME_SEPERATOR = " -- "

def _truncate_object_name(name: str) -> str:

    MAX_NAME_LENGTH = OBJECT_NAME_MAX_LENGTH - SPECKLE_ID_LENGTH - len(OBJECT_NAME_SEPERATOR)

    return name[:MAX_NAME_LENGTH]
    

def _simplified_speckle_type(speckle_type: str) -> str:
    return(speckle_type.rsplit('.')[-1]) #Take only the most specific object type name (without namespace)

def _generate_object_name(speckle_object: Base) -> str:
    prefix: str
    name = _get_friendly_object_name(speckle_object)
    if name:
        prefix = _truncate_object_name(name)
    else:
        prefix = _simplified_speckle_type(speckle_object.speckle_type)

    return f"{prefix}{OBJECT_NAME_SEPERATOR}{speckle_object.id}"


def get_scale_factor(speckle_object: Base, fallback: float = 1.0) -> float:
    scale = fallback
    if units := getattr(speckle_object, "units", None):
        scale = get_scale_length(units) / bpy.context.scene.unit_settings.scale_length
    return scale