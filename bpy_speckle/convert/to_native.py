import math
from typing import Any, Dict, Iterable, List, Optional, Union, Collection, cast
from bpy_speckle.convert.constants import DISPLAY_VALUE_PROPERTY_ALIASES, ELEMENTS_PROPERTY_ALIASES, OBJECT_NAME_MAX_LENGTH, OBJECT_NAME_SEPERATOR, SPECKLE_ID_LENGTH
from bpy_speckle.functions import get_default_traversal_func, get_scale_length, _report
from bpy_speckle.convert.util import ConversionSkippedException
from mathutils import (
    Matrix as MMatrix,
    Vector as MVector,
    Quaternion as MQuaternion,
)
import bpy, bmesh
from specklepy.objects.other import (
    Collection as SCollection,
    Instance,
    Transform,
    BlockDefinition,
)
from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh, Line, Polyline, Curve, Arc, Polycurve, Ellipse, Circle, Plane
from bpy.types import Object, Collection as BCollection

from .util import (
    add_to_heirarchy,
    get_render_material,
    get_vertex_color_material,
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
    
    #TODO: Check usages handle exceptions

def convert_to_native(speckle_object: Base) -> Object:

    speckle_type = type(speckle_object)

    object_name = _generate_object_name(speckle_object)
    scale = get_scale_factor(speckle_object)

    converted: Union[bpy.types.ID, bpy.types.Object, None] = None
    children: list[Object] = []

    # convert elements/breps
    if not _has_native_convesion(speckle_object):
        (converted, children) = display_value_to_native(speckle_object, object_name, scale)
        if not converted and not children:
            raise Exception(f"Zero geometry converted from displayValues for {speckle_object}")

    # convert supported geometry
    elif isinstance(speckle_object, Mesh):
        converted = mesh_to_native(speckle_object, object_name, scale)
    elif speckle_type in SUPPORTED_CURVES:
        converted = icurve_to_native(speckle_object, object_name, scale)
    elif "View" in speckle_object.speckle_type:
         return view_to_native(speckle_object, object_name, scale)
    elif isinstance(speckle_object, Instance):
        if convert_instances_as == "linked_duplicates":
           converted = instance_to_native_object(speckle_object, scale)
        elif convert_instances_as == "collection_instance":
            converted = instance_to_native_collection_instance(speckle_object, scale)
        else:
            _report(f"convert_instances_as = '{convert_instances_as}' is not implemented, Instances will be converted as collection instances!")
            converted = instance_to_native_collection_instance(speckle_object, scale)
    else:
        raise Exception(f"Unsupported type {speckle_type}")


    if not isinstance(converted, Object):
        converted = create_new_object(converted, object_name)
    
    converted.speckle.object_id = str(speckle_object.id) # type: ignore
    converted.speckle.enabled = True # type: ignore
    add_custom_properties(speckle_object, converted)

    for c in children:
        c.parent = converted

    return converted



def display_value_to_native(speckle_object: Base, name: str, scale: float) -> tuple[Optional[bpy.types.Mesh], list[bpy.types.Object]]:
    return _members_to_native(speckle_object, name, scale, DISPLAY_VALUE_PROPERTY_ALIASES, True)

def elements_to_native(speckle_object: Base, name: str, scale: float) -> list[bpy.types.Object]:
    (_, elements) = _members_to_native(speckle_object, name, scale, ELEMENTS_PROPERTY_ALIASES, False)
    return elements

def _members_to_native(speckle_object: Base, name: str, scale: float, members: Iterable[str], combineMeshes: bool) -> tuple[Optional[bpy.types.Mesh], list[bpy.types.Object]]:
    """
    Converts a given speckle_object by converting specified members

    if combineMeshes == True
        Converts mesh members as one mesh
        Converts non-mesh members as child Objects
    if combineMeshes == False
        Converts all members as child objects (first item of the returned tuple will be None)
    :returns: converted mesh, and any other converted child objects (may happen if members contained non-meshes)
    """
    meshes: list[Mesh] = []
    others: list[Base] = []

    for alias in members:
        display = getattr(speckle_object, alias, None)

        count = 0
        MAX_DEPTH = 255 # some large value, to prevent infinite reccursion
        def seperate(value: Any) -> bool:
            nonlocal meshes, others, count, MAX_DEPTH

            if combineMeshes and isinstance(value, Mesh):
                meshes.append(value)
            elif isinstance(value, Base):
                others.append(value)
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


    children: list[Object] = []
    mesh = None

    if meshes:
        mesh = meshes_to_native(speckle_object, meshes, name, scale) #TODO: reconsider passing scale around...

    for item in others:
        try:
            blender_object = convert_to_native(item)
            children.append(blender_object)
        except Exception as ex:
            _report(f"Failed to convert display value {item}: {ex}")

    return (mesh, children)



def view_to_native(speckle_view, name: str, scale: float) -> bpy.types.Object:
    native_cam: bpy.types.Camera
    if name in bpy.data.cameras.keys():
         native_cam = bpy.data.cameras[name]
    else:
        native_cam = bpy.data.cameras.new(name=name)
        native_cam.lens = 18 # 90° horizontal fov

    if not hasattr(speckle_view, "origin"):
        raise ConversionSkippedException("2D views not supported")

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
        if not mesh.vertices: continue

        add_faces(mesh, bm, offset, i)

        try:
            render_material = get_render_material(mesh) or fallback_material
            if render_material is not None:
                native_material = render_material_to_native(render_material)
                blender_mesh.materials.append(native_material)
            elif mesh.colors:
                native_material = get_vertex_color_material()
                blender_mesh.materials.append(native_material)
        except Exception as ex:
            _report(f"Failed converting render material for {name}: {ex}")

        offset += len(mesh.vertices) // 3

    bm.faces.ensure_lookup_table()
    bm.verts.index_update()

    # Third pass, add vertex instance data
    for mesh in meshes:
        try:
            add_colors(mesh, bm)
        except Exception as ex:
            _report(f"Skipping converting vertex colors for {name}: {ex}")
            
        try:
            add_uv_coords(mesh, bm)
        except Exception as ex:
            _report(f"Skipping converting uv coordinates for {name}: {ex}")

    bm.to_mesh(blender_mesh)
    bm.free()  

    return blender_mesh


"""
Curves
"""

def line_to_native(speckle_curve: Line, blender_curve: bpy.types.Curve, scale: float) -> List[bpy.types.Spline]:
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


def polyline_to_native(scurve: Polyline, bcurve: bpy.types.Curve, scale: float) -> List[bpy.types.Spline]:
    if not (value := scurve.value): return []
    N = len(value) // 3

    polyline = bcurve.splines.new("POLY")

    if hasattr(scurve, "closed"):
        polyline.use_cyclic_u = scurve.closed or False

    polyline.points.add(N - 1)
    for i in range(N):
        polyline.points[i].co = (
            float(value[i * 3]) * scale,
            float(value[i * 3 + 1]) * scale,
            float(value[i * 3 + 2]) * scale,
            1,
        )

    return [polyline]
    


def nurbs_to_native(scurve: Curve, bcurve: bpy.types.Curve, scale: float) -> List[bpy.types.Spline]:
    if not (points := scurve.points): return []
    if not scurve.degree: raise Exception("curve is missing degree")
    if not scurve.weights: raise Exception("curve is missing weights")

    # Closed curves from rhino will have n + degree points. We ignore the extras
    num_points = len(points) // 3 - scurve.degree if (scurve.closed) else (
        len(points) // 3)   
    
    nurbs = bcurve.splines.new("NURBS")
    nurbs.use_cyclic_u = scurve.closed or False
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
    if not rcurve.radius: raise Exception("curve is missing radius")
    if not rcurve.startAngle: raise Exception("curve is missing startAngle")
    if not rcurve.endAngle: raise Exception("curve is missing endAngle")

    plane = rcurve.plane
    if not plane:
        return None

    normal = MVector([plane.normal.x, plane.normal.y, plane.normal.z])

    radius = rcurve.radius * scale
    startAngle = rcurve.startAngle
    endAngle = rcurve.endAngle

    startQuat = MQuaternion(normal, startAngle) # type: ignore
    endQuat = MQuaternion(normal, endAngle) # type: ignore

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
    stepQuat = MQuaternion(normal, step) # type: ignore
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
    if not scurve.segments: raise Exception("curve is missing segments")

    curves = []

    for seg in scurve.segments:
        speckle_type = type(seg)

        if speckle_type in SUPPORTED_CURVES:
            curves.append(icurve_to_native_spline(seg, bcurve, scale))
        else:
            _report(f"Unsupported curve type: {speckle_type}")

    return curves
 
def ellipse_to_native(ellipse: Union[Ellipse, Circle], bcurve: bpy.types.Curve, units_scale: float) -> List[bpy.types.Spline]:
    if not ellipse.plane: raise Exception("curve is missing plane")

    radX: float
    radY: float
    if isinstance(ellipse, Ellipse):
        if not ellipse.firstRadius: raise Exception("curve is missing firstRadius")
        if not ellipse.secondRadius: raise Exception("curve is missing secondRadius")

        radX = ellipse.firstRadius * units_scale
        radY = ellipse.secondRadius * units_scale
    else:
        if not ellipse.radius: raise Exception("curve is missing radius")

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
        spline.bezier_points[i].co = transform @ MVector(points[i]) # type: ignore
        spline.bezier_points[i].handle_left = transform @ MVector(left_handles[i]) # type: ignore
        spline.bezier_points[i].handle_right = transform @ MVector(right_handles[i]) # type: ignore

    spline.use_cyclic_u = True
    
    #TODO support trims?
    return [spline]


def icurve_to_native_spline(speckle_curve: Base, blender_curve: bpy.types.Curve, scale: float) -> List[bpy.types.Spline]:
    # polycurves
    if isinstance(speckle_curve, Polycurve):
        return polycurve_to_native(speckle_curve, blender_curve, scale)

    splines: List[bpy.types.Spline]
    # single curves
    if isinstance(speckle_curve, Line):
        splines = line_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Curve):
        splines = nurbs_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Polyline):
        splines = polyline_to_native(speckle_curve, blender_curve, scale)
    elif isinstance(speckle_curve, Arc):
        spline = arc_to_native(speckle_curve, blender_curve, scale)
        splines = [spline] if spline else []
    elif isinstance(speckle_curve, Ellipse) or isinstance(speckle_curve, Circle):
        splines = ellipse_to_native(speckle_curve, blender_curve, scale)
    else:
        raise TypeError(f"{speckle_curve} is not a supported curve type. Supported types: {SUPPORTED_CURVES}")

    return splines


def icurve_to_native(speckle_curve: Base, name: str, scale: float) -> bpy.types.Curve:
    curve_type = type(speckle_curve)
    if curve_type not in SUPPORTED_CURVES:
        raise Exception(f"Unsupported curve type: {curve_type}")

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
        mat[i][3] *= scale # type: ignore
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
    if not instance.definition: raise Exception("Instance is missing a definition")
    name_prefix = (
        _get_friendly_object_name(instance) 
        or _get_friendly_object_name(instance.definition) 
        or _simplified_speckle_type(instance.speckle_type)
    )
    return f"{name_prefix}{OBJECT_NAME_SEPERATOR}{instance.id}"


def instance_to_native_object(instance: Instance, scale: float) -> Object:
    """
    Converts Instance to a unique object with (potentially) shared data (linked duplicate)
    """
    if not instance.definition: raise Exception("Instance is missing a definition")
    if not instance.transform: raise Exception("Instance is missing a transform")
    definition = instance.definition
    if not definition.id: raise Exception("Instance is missing a valid definition")

    name = _get_instance_name(instance)

    native_instance: Optional[Object] = None
    converted_objects: Dict[str, Union[Object, BCollection]] = {}
    traversal_root: Base = definition
    
    if not can_convert_to_native(definition):
        # Non-convertable (like all blocks, and some revit instances) will not be converted as part of the deep_traversal.
        # so we explicitly convert them as empties.
        native_instance = create_new_object(None, name) 
        native_instance.empty_display_size = 0

        converted_objects["__ROOT"] = native_instance # we create a dummy root to avoid id conflicts, since revit definitions have displayValues, they are convertable
        traversal_root = Base(elements=definition, id="__ROOT")

    #Convert definition + "elements" on definition
    _deep_conversion(traversal_root, converted_objects, False)

    if not native_instance:
        assert(can_convert_to_native(definition))

        if not definition.id in converted_objects:
            raise Exception("Definition was not converted")

        converted = converted_objects[definition.id]

        if not isinstance(converted, Object):
            raise Exception("Definition was not converted to an Object")
        
        native_instance = converted

    instance_transform = transform_to_native(instance.transform, scale)
    native_instance.matrix_world = instance_transform

    return native_instance

def instance_to_native_collection_instance(instance: Instance, scale: float) -> bpy.types.Object:
    """
    Convert an Instance as a transformed Object with the `instance_collection` property
    set to be the `instance.Definition` converted as a collection

    The definition collection won't be linked to the current scene
    Any Elements on the instance object will also be converted (and spacially transformed)
    """
    if not instance.definition: raise Exception("Instance is missing a definition")
    if not instance.transform: raise Exception("Instance is missing a transform")

    name = _get_instance_name(instance)

    # Get/Convert definition collection
    collection_def = _instance_definition_to_native(instance.definition)

    instance_transform = transform_to_native(instance.transform, scale)

    native_instance = bpy.data.objects.new(name, None)

    #add_custom_properties(instance, native_instance)
    # hide the instance axes so they don't clutter the viewport
    native_instance.empty_display_size = 0
    native_instance.instance_collection = collection_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world = instance_transform
        
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

    converted_objects = {}
    converted_objects["__ROOT"] = native_def # we create a dummy root to avoid id conflicts, since revit definitions have displayValues, they are convertable
    dummyRoot = Base(elements=definition, id="__ROOT")

    _deep_conversion(dummyRoot, converted_objects, True)

    return native_def

def _deep_conversion(root: Base, converted_objects: Dict[str, Union[Object, BCollection]], preserve_transform: bool):
    traversal_func = get_default_traversal_func(can_convert_to_native)

    for item in traversal_func.traverse(root):
        
        current: Base = item.current
        if can_convert_to_native(current) or isinstance(current, SCollection):
            try:
                if not current or not current.id: raise Exception(f"{current} was an invalid speckle object")

                #Convert the object!
                converted_data_type: str
                converted: Union[Object, BCollection, None]
                if isinstance(current, SCollection):
                    if(current.collectionType == "Scene Collection"): raise ConversionSkippedException()
                    converted = collection_to_native(current)
                    converted_data_type = "COLLECTION"
                else:
                    converted = convert_to_native(current)
                    converted_data_type = "COLLECTION_INSTANCE" if converted.instance_collection else str(converted.type)
                
                if converted is None:
                    raise Exception("Conversion returned None")
                    
                converted_objects[current.id] = converted

                add_to_heirarchy(converted, item, converted_objects, preserve_transform)

                _report(f"Successfully converted {type(current).__name__} {current.id} as '{converted_data_type}'")
            except ConversionSkippedException as ex:
                _report(f"Skipped converting {type(current).__name__} {current.id}: {ex}")
            except Exception as ex:
                _report(f"Failed to converted {type(current).__name__} {current.id}: {ex}")

def collection_to_native(collection: SCollection) -> BCollection: 
    name = collection.name or f"{collection.collectionType} -- {collection.applicationId or collection.id}"  #TODO: consider consolidating name formatting with Rhino
    ret =  get_or_create_collection(name)

    color = getattr(collection, "colorTag", None)
    if color:
        ret.color_tag = color

    return ret

def get_or_create_collection(name: str, clear_collection: bool = True) -> BCollection:
    existing = cast(BCollection, bpy.data.collections.get(name))
    if existing:
        if clear_collection:
            for obj in existing.objects:
                existing.objects.unlink(obj)
        return existing
    else:
        new_collection = bpy.data.collections.new(name)

        #NOTE: We want to not render revit "Rooms" collections by default.
        if name == "Rooms":
            new_collection.hide_viewport = True
            new_collection.hide_render = True

        return new_collection
    
    

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