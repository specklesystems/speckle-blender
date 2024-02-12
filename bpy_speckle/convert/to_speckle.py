from typing import Dict, Iterable, List, Optional, Tuple, Union, cast
import bpy
from bpy.types import (
    Depsgraph, 
    MeshPolygon, 
    Object, 
    Curve as NCurve,
    Mesh as NMesh,
    Camera as NCamera,
)
from deprecated import deprecated
from mathutils.geometry import interpolate_bezier
from mathutils import (
    Matrix as MMatrix,
    Vector as MVector,
)
from specklepy.objects import Base
from specklepy.objects.other import BlockInstance, BlockDefinition, RenderMaterial, Transform
from specklepy.objects.geometry import (
     Mesh, Curve, Interval, Box, Point, Vector, Polyline,
)
from bpy_speckle.blender_commit_object_builder import BlenderCommitObjectBuilder
from bpy_speckle.convert.constants import OBJECT_NAME_SPECKLE_SEPARATOR, SPECKLE_ID_LENGTH
from bpy_speckle.convert.util import (
    ConversionSkippedException,
    get_blender_custom_properties,
    make_knots,
    nurb_make_curve,
    to_argb_int,
)
from bpy_speckle.functions import _report


Units: str = "m" # The desired final units to send
UnitsScale: float = 1 # The scale factor conversions need to apply to position data to get to the desired units

CAN_CONVERT_TO_SPECKLE = ("MESH", "CURVE", "EMPTY", "CAMERA", "FONT", "SURFACE", "META")


def convert_to_speckle(raw_blender_object: Object, units_scale: float, units: str, depsgraph: Optional[Depsgraph]) -> Base:
    """
    Converts supported 1 blender objects to 1 speckle object (potentially with children)
    :param raw_blender_object: the blender object (unevaluated by a Depsgraph) to convert
    :param units_scale: The scale factor conversions need to apply to position data to get to the desired units
    :param units: The desired final units to send
    :param depsgraph: Optional depsgraph if provided will evaluate modifiers on geometry data
    :return: The Converted blender object
    """
    global Units, UnitsScale
    Units = units
    UnitsScale = units_scale
    
    blender_type = raw_blender_object.type
    if blender_type not in CAN_CONVERT_TO_SPECKLE:
        raise ConversionSkippedException(f"Objects of type {blender_type} are not supported")

    blender_object = cast(Object, (
        raw_blender_object.evaluated_get(depsgraph)
        if depsgraph
        else raw_blender_object
        ))

    converted: Optional[Base] = None
    if blender_type == "MESH":
        converted = mesh_to_speckle(blender_object, cast(NMesh, blender_object.data))
    elif blender_type == "CURVE":
        converted = curve_to_speckle(blender_object, cast(NCurve, blender_object.data))
    elif blender_type == "EMPTY":
        converted = empty_to_speckle(blender_object)
    elif blender_type == "CAMERA":
        converted = camera_to_speckle_view(blender_object, cast(NCamera, blender_object.data))
    elif blender_type == "FONT" or "SURFACE" or "META":
        converted = anything_to_speckle_mesh(blender_object)
    if not converted:
        raise Exception("Conversion returned None")

    converted["properties"] = get_blender_custom_properties(raw_blender_object) #NOTE: Depsgraph copies don't have custom properties so we use the raw version

    # Set object transform #TODO: this could be deprecated once we add proper geometry instancing support
    if blender_type != "EMPTY": 
        converted["properties"]["transform"] = transform_to_speckle(
            blender_object.matrix_world
        )

    return converted

def mesh_to_speckle(blender_object: Object, data: bpy.types.Mesh) -> Base:
    b = Base()
    b["name"] = to_speckle_name(blender_object)
    b["@displayValue"] = mesh_to_speckle_meshes(blender_object, data)
    return b

def mesh_to_speckle_meshes(blender_object: Object, data: bpy.types.Mesh) -> List[Mesh]:

    # Categorise polygons by material index
    submesh_data: Dict[int, List[MeshPolygon]] = {}

    for p in data.polygons:
        if p.material_index not in submesh_data:
            submesh_data[p.material_index] = []
        submesh_data[p.material_index].append(p)

    transform = cast(MMatrix, blender_object.matrix_world)
    scaled_vertices = [tuple(transform @ x.co * UnitsScale) for x in data.vertices] 

    # Create Speckle meshes for each material
    submeshes = []
    index_counter = 0
    for i in submesh_data:
        index_mapping: Dict[int, int] = {}

        #Loop through each polygon, and map indices to their new index in m_verts
    
        mesh_area = 0
        m_verts: List[float] = []
        m_faces: List[int] = []
        m_texcoords: List[float] = []
        for face in submesh_data[i]:
            u_indices = face.vertices
            m_faces.append(len(u_indices))

            mesh_area += face.area
            for u_index in u_indices:
                if u_index not in index_mapping:
                    # Create mapping between index in blender mesh, and new index in speckle submesh
                    index_mapping[u_index] = len(m_verts) // 3
                    vert = scaled_vertices[u_index]
                    m_verts.append(vert[0])
                    m_verts.append(vert[1])
                    m_verts.append(vert[2])
                
                if data.uv_layers.active:
                    vt = data.uv_layers.active.data[index_counter]
                    uv = cast(MVector, vt.uv)
                    m_texcoords.extend([uv.x, uv.y])

                m_faces.append(index_mapping[u_index])
                index_counter += 1

        speckle_mesh = Mesh(
            vertices=m_verts,
            faces=m_faces,
            colors=[],
            textureCoordinates=m_texcoords,
            units=Units,
            area = mesh_area,
            bbox=Box(area=0.0, volume=0.0),
        )
        
        if i < len(data.materials):
            material = data.materials[i]
            if material is not None:
                speckle_mesh["renderMaterial"] = material_to_speckle(material)
        submeshes.append(speckle_mesh)           

    return submeshes


def bezier_to_speckle(matrix: MMatrix, spline: bpy.types.Spline, name: Optional[str] = None) -> Curve:
    degree = 3
    closed = spline.use_cyclic_u
    points: List[Tuple[MVector]] = []
    for i, bp in enumerate(spline.bezier_points):
        if i > 0:
            points.append(tuple(matrix @ bp.handle_left * UnitsScale)) # type: ignore
        points.append(tuple(matrix @ bp.co * UnitsScale)) # type: ignore
        if i < len(spline.bezier_points) - 1:
            points.append(tuple(matrix @ bp.handle_right * UnitsScale)) # type: ignore

    if closed:
        points.extend(
            (
                tuple(matrix @ spline.bezier_points[-1].handle_right * UnitsScale), # type: ignore
                tuple(matrix @ spline.bezier_points[0].handle_left * UnitsScale), # type: ignore
                tuple(matrix @ spline.bezier_points[0].co * UnitsScale), # type: ignore
            )
        )
    
    num_points = len(points)

    flattened_points = []
    for row in points: flattened_points.extend(row)

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
        periodic= not spline.use_endpoint_u,
        points=flattened_points,
        weights=[1] * num_points,
        knots=knots,
        rational=True,
        area=0,
        volume=0,
        length=length,
        domain=domain,
        units=Units,
        bbox=Box(area=0.0, volume=0.0),
        displayValue = bezier_to_speckle_polyline(matrix, spline, length),
    )


def nurbs_to_speckle(matrix: MMatrix, spline: bpy.types.Spline, name: Optional[str] = None) -> Curve:

    degree = spline.order_u - 1
    knots = make_knots(spline)

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)

    weights = [pt.weight for pt in spline.points]
    is_rational = all(w == weights[0] for w in weights)

    points = [tuple(matrix @ pt.co.xyz * UnitsScale) for pt in spline.points] # type: ignore

    flattened_points = []
    for row in points: flattened_points.extend(row)

    if spline.use_cyclic_u:
        for i in range(0, degree * 3, 3):
            # Rhino expects n + degree number of points (for closed curves). So we need to add an extra point for each degree
            flattened_points.append(flattened_points[i + 0])
            flattened_points.append(flattened_points[i + 1])
            flattened_points.append(flattened_points[i + 2])
        
        for i in range(0, degree):
            weights.append(weights[i])

    return Curve(
        name=name,
        degree=degree,
        closed=spline.use_cyclic_u,
        periodic= not spline.use_endpoint_u,
        points=flattened_points,
        weights=weights,
        knots=knots,
        rational=is_rational, 
        area=0,
        volume=0,
        length=length,
        domain=domain,
        units=Units,
        bbox=Box(area=0.0, volume=0.0),
        displayValue=nurbs_to_speckle_polyline(matrix, spline, length),
    )

def nurbs_to_speckle_polyline(matrix: MMatrix, spline: bpy.types.Spline, length: Optional[float] = None) -> Polyline:
    """
    Samples a nurbs curve with resolution_u creating a polyline
    """
    points: List[float] = []
    sampled_points = nurb_make_curve(spline, spline.resolution_u, 3)
    for i in range(0, len(sampled_points), 3):
        scaled_point = cast(Vector, matrix @ MVector((
        sampled_points[i + 0],
        sampled_points[i + 1],
        sampled_points[i + 2])) * UnitsScale)

        points.append(scaled_point.x)
        points.append(scaled_point.y)
        points.append(scaled_point.z)
        
    length = length or spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Polyline(value=points, closed = spline.use_cyclic_u, domain=domain, area=0, len=length)


#Inspired by https://blender.stackexchange.com/a/689 (CC BY-SA 3.0) 
def bezier_to_speckle_polyline(matrix: MMatrix, spline: bpy.types.Spline, length: Optional[float] = None) -> Optional[Polyline]:
    """
    Samples a Bézier curve with resolution_u creating a polyline
    """
    segments = len(spline.bezier_points)
    if segments < 2: return None

    R = spline.resolution_u + 1

    points = []
    if not spline.use_cyclic_u:
        segments -= 1
    
    points: List[float] = []
    for i in range(segments):
        inext = (i + 1) % len(spline.bezier_points)

        knot1 = spline.bezier_points[i].co
        handle1 = spline.bezier_points[i].handle_right
        handle2 = spline.bezier_points[inext].handle_left
        knot2 = spline.bezier_points[inext].co

        _points = interpolate_bezier(knot1, handle1, handle2, knot2, R)
        for p in _points:
            scaled_point = matrix @ p * UnitsScale
            points.append(scaled_point.x)
            points.append(scaled_point.y)
            points.append(scaled_point.z)

    length = length or spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Polyline(value=points, closed = spline.use_cyclic_u, domain=domain, area=0, len=length)

_QUICK_TEST_NAME_LENGTH = SPECKLE_ID_LENGTH + len(OBJECT_NAME_SPECKLE_SEPARATOR)

def to_speckle_name(blender_object: bpy.types.ID) -> str:
    does_name_contain_id = len(blender_object.name) > _QUICK_TEST_NAME_LENGTH and OBJECT_NAME_SPECKLE_SEPARATOR in blender_object.name
    if does_name_contain_id:
        return blender_object.name.rsplit(OBJECT_NAME_SPECKLE_SEPARATOR, 1)[0]
    else:
        return blender_object.name

def poly_to_speckle(matrix: MMatrix, spline: bpy.types.Spline, name: Optional[str] = None) -> Polyline:
    points = [tuple(matrix @ pt.co.xyz * UnitsScale) for pt in spline.points] # type: ignore

    flattened_points = []
    for row in points: flattened_points.extend(row)

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Polyline(
        name=name,
        closed=bool(spline.use_cyclic_u),
        value=list(flattened_points),
        length=length,
        domain=domain,
        bbox=Box(area=0.0, volume=0.0),
        area=0,
        units=Units,
    )


def curve_to_speckle(blender_object: Object, data: bpy.types.Curve) -> Base:
    b = Base()
    (meshes, curves) = curve_to_speckle_geometry(blender_object, data)
    if meshes:
        b["@displayValue"] = meshes

    b["name"] = to_speckle_name(blender_object)
    b["@elements"] = curves
    return b

def curve_to_speckle_geometry(blender_object: Object, data: bpy.types.Curve) -> Tuple[List[Mesh], List[Base]]:
    assert(blender_object.type == "CURVE")

    blender_object = cast(Object, blender_object.evaluated_get(bpy.context.view_layer.depsgraph))

    matrix = cast(MMatrix, blender_object.matrix_world)

    meshes: List[Mesh] = []
    curves: List[Base] = []

    #TODO: Could we support this better?
    if data.bevel_mode == "OBJECT" and data.bevel_object != None:
        meshes = mesh_to_speckle_meshes(blender_object, blender_object.to_mesh())

    for spline in data.splines:
        if spline.type == "BEZIER":
            curves.append(bezier_to_speckle(matrix, spline, to_speckle_name(blender_object)))

        elif spline.type == "NURBS":
            curves.append(nurbs_to_speckle(matrix, spline, to_speckle_name(blender_object)))

        elif spline.type == "POLY":
            curves.append(poly_to_speckle(matrix, spline, to_speckle_name(blender_object)))

    return (meshes, curves)

def anything_to_speckle_mesh(blender_object: Object) -> Base:

    mesh = mesh_to_speckle(blender_object, blender_object.to_mesh())
    blender_object.to_mesh_clear()
    return mesh

@deprecated
def ngons_to_speckle_polylines(blender_object: Object, data: bpy.types.Mesh) -> Optional[List[Polyline]]:
    UNITS = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

    if blender_object.type != "MESH":
        return None

    mat = blender_object.matrix_world

    verts = data.vertices
    polylines = []
    for i, poly in enumerate(data.polygons):
        value = []
        for v in poly.vertices:
            value.extend(mat @ verts[v].co * UnitsScale) # type: ignore

        domain = Interval(start=0, end=1)
        poly = Polyline(
            name="{}_{}".format(blender_object.name, i),
            closed=True,
            value=value,
            length=0,
            domain=domain,
            bbox=Box(area=0.0, volume=0.0),
            area=0,
            units=UNITS,
        )

        polylines.append(poly)

    return polylines


def material_to_speckle(blender_mat: bpy.types.Material) -> RenderMaterial:
    speckle_mat = RenderMaterial()
    speckle_mat.name = blender_mat.name

    if blender_mat.use_nodes:
        if blender_mat.node_tree.nodes.get("Principled BSDF"):
            inputs = blender_mat.node_tree.nodes["Principled BSDF"].inputs
            emission_color = "Emission" if "Emission" in inputs else "Emission Color" # type: ignore 
            
            speckle_mat.diffuse = to_argb_int(inputs["Base Color"].default_value) # type: ignore
            speckle_mat.emissive = to_argb_int(inputs[emission_color].default_value) # type: ignore
            speckle_mat.roughness = inputs["Roughness"].default_value # type: ignore
            speckle_mat.metalness = inputs["Metallic"].default_value # type: ignore
            speckle_mat.opacity = inputs["Alpha"].default_value # type: ignore
            return speckle_mat
        elif blender_mat.node_tree.nodes.get("Diffuse BSDF"):
            inputs = blender_mat.node_tree.nodes["Diffuse BSDF"].inputs
            speckle_mat.diffuse = to_argb_int(inputs["Color"].default_value) # type: ignore
            speckle_mat.roughness = inputs["Roughness"].default_value # type: ignore
            return speckle_mat
        #TODO: Support more shaders

    # fallback to standard material props
    speckle_mat.diffuse = to_argb_int(blender_mat.diffuse_color) # type: ignore
    speckle_mat.metalness = blender_mat.metallic
    speckle_mat.roughness = blender_mat.roughness

    return speckle_mat

def camera_to_speckle_view(blender_object: Object, data: NCamera) -> Base:
    if data.type != 'PERSP':
        raise Exception(f"Cameras of type {data.type} are not currently supported")
    
    matrix = cast(MMatrix, blender_object.matrix_world)
    up = cast(MVector, matrix.col[1].xyz)
    forwards = cast(MVector, -matrix.col[2].xyz)
    translation = matrix.translation

    view = Base.of_type("Objects.BuiltElements.View:Objects.BuiltElements.View3D") #HACK: views are not in specklepy yet!
    view.name = to_speckle_name(blender_object)
    view.origin = vector_to_speckle_point(translation)
    view.upDirection = vector_to_speckle(up)
    view.forwardDirection = vector_to_speckle(forwards)
    view.target = vector_to_speckle_point(forwards) #TODO: do these need to be scaled?
    view.units = Units
    view.isOrthogonal = False
    return view

def vector_to_speckle_point(xyz: MVector) -> Point:
    return Point(
        x = xyz.x * UnitsScale,
        y = xyz.y * UnitsScale,
        z = xyz.z * UnitsScale,
        units = Units,
        )

def vector_to_speckle(xyz: MVector) -> Vector:
    return Vector(
        x = xyz.x * UnitsScale,
        y = xyz.y * UnitsScale,
        z = xyz.z * UnitsScale,
        units = Units,
        )

def transform_to_speckle(blender_transform: Union[Iterable[Iterable[float]], MMatrix]) -> Transform:
    iterable_transform = cast(Iterable[Iterable[float]], blender_transform) #NOTE: Matrix are iterable, even if type hinting says they are not
    value = [y for x in iterable_transform for y in x]
    # scale the translation
    for i in (3, 7, 11):
        value[i] *= UnitsScale

    return Transform(value=value, units=Units)


def block_def_to_speckle(blender_definition: bpy.types.Collection) -> BlockDefinition:
    geometryBuilder = BlenderCommitObjectBuilder()
    for geo in blender_definition.objects:
        try:
            c = convert_to_speckle(geo, UnitsScale, Units, None)
            geometryBuilder.include_object(c, geo)
        except ConversionSkippedException as ex:
            _report(f"Skipped converting '{geo.name_full}' inside collection instance: '{ex}")
        except Exception as ex:
            _report(f"Failed to converted '{geo.name_full}' inside collection instance: '{ex}'")

    dummyRoot = Base()
    geometryBuilder.apply_relationships(geometryBuilder.converted.values(), dummyRoot)

    block_def = BlockDefinition(
        units=Units,
        name=to_speckle_name(blender_definition),
        geometry=dummyRoot["@elements"],
        basePoint=Point(units=Units),
    )
    # blender_props = get_blender_custom_properties(blender_definition)
    # block_def.applicationId = blender_props.pop("applicationId", None) #TODO: remove?
    return block_def


def block_instance_to_speckle(blender_instance: Object) -> BlockInstance:
    return BlockInstance(
        blockDefinition=block_def_to_speckle(
            blender_instance.instance_collection
        ),
        transform=transform_to_speckle(blender_instance.matrix_world),
        name=to_speckle_name(blender_instance),
        units=Units,
    )


def empty_to_speckle(blender_object: Object) -> Union[BlockInstance, Base]:
    # probably an instance collection (block) so let's try it

    if blender_object.instance_collection and blender_object.instance_type == "COLLECTION":
        # Empty -> Block
        return block_instance_to_speckle(blender_object)
    else:
        # Empty -> Point
        wrapper = Base()
        wrapper["@displayValue"] = matrix_to_speckle_point(cast(MMatrix, blender_object.matrix_world))
        return wrapper


def matrix_to_speckle_point(matrix: MMatrix, units_scale: float = 1.0) -> Point:
    transformed_pos = cast(MVector, matrix @ MVector((0,0,0)) * units_scale)
    return Point(x = transformed_pos.x,
                 y = transformed_pos.y, 
                 z = transformed_pos.z)