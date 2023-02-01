from typing import Dict, Iterable, Optional, Tuple
import bpy
from bpy.types import Depsgraph, Material, MeshPolygon, Object
from specklepy.objects.geometry import Mesh, Curve, Interval, Box, Point, Polyline
from specklepy.objects.other import *
from bpy_speckle.functions import _report
from bpy_speckle.convert.util import (
    get_blender_custom_properties,
    make_knots,
    to_argb_int,
)

UNITS = "m"

CAN_CONVERT_TO_SPECKLE = ("MESH", "CURVE", "EMPTY")


def convert_to_speckle(blender_object: Object, scale: float, units: str, desgraph: Optional[Depsgraph]) -> Optional[list]:
    global UNITS
    UNITS = units
    blender_type = blender_object.type
    if blender_type not in CAN_CONVERT_TO_SPECKLE:
        return None

    speckle_objects = []
    # speckle_material = material_to_speckle_old(blender_object) #TODO: What about curves with materials...
    if desgraph:
        blender_object = blender_object.evaluated_get(desgraph)
    converted = None
    if blender_type == "MESH":
        converted = mesh_to_speckle(blender_object, blender_object.data, scale)
    elif blender_type == "CURVE":
        converted = icurve_to_speckle(blender_object, blender_object.data, scale)
    elif blender_type == "EMPTY":
        converted = empty_to_speckle(blender_object, scale)
    if not converted:
        return None

    if isinstance(converted, list):
        speckle_objects.extend([c for c in converted if c != None])
    else:
        speckle_objects.append(converted)

    for so in speckle_objects:
        so.properties = get_blender_custom_properties(blender_object)
        so.applicationId = so.properties.pop("applicationId", None)


        # Set object transform
        if blender_type != "EMPTY":
            so.properties["transform"] = transform_to_speckle(
                blender_object.matrix_world
            )

    return speckle_objects

def mesh_to_speckle(blender_object: Object, data: bpy.types.Mesh, scale: float = 1.0) -> List[Mesh]:
    #if data.loop_triangles is None or len(data.loop_triangles) < 1:
    #    data.calc_loop_triangles()

    # Categorise polygons by material index
    submesh_data: Dict[int, List[MeshPolygon]] = {}

    for p in data.polygons:
        if p.material_index not in submesh_data:
            submesh_data[p.material_index] = []
        submesh_data[p.material_index].append(p)

    transform = blender_object.matrix_world
    scaled_vertices = [tuple(transform @ x.co * scale) for x in data.vertices]

    # Create Speckle meshes for each material
    submeshes = []
    index_counter = 0
    for i in submesh_data:
        index_mapping: Dict[int, int] = {}

        #Loop through each polygon, and map indicies to their new index in m_verts
    
        m_verts: List[float] = []
        m_faces: List[int] = []
        m_texcoords: List[float] = []
        for face in submesh_data[i]:
            u_indices = face.vertices
            m_faces.append(len(u_indices))
            for u_index in u_indices:
                if u_index not in index_mapping:
                    # Create mapping between index in blender mesh, and new index in speckle submesh
                    index_mapping[u_index] = len(m_verts) // 3
                    vert = scaled_vertices[u_index]
                    m_verts.append(vert[0])
                    m_verts.append(vert[1])
                    m_verts.append(vert[2])
                
                #if data.uv_layers.active:
                #    vt = data.uv_layers.active.data[index_counter]
                #    m_texcoords.extend([vt.uv.x, vt.uv.y])

                m_faces.append(index_mapping[u_index])
                index_counter += 1

        speckle_mesh = Mesh(
            vertices=m_verts,
            faces=m_faces,
            colors=[],
            textureCoordinates=m_texcoords,
            units=UNITS,
            bbox=Box(area=0.0, volume=0.0),
        )
        
        if i < len(data.materials):
            material = data.materials[i]
            if material is not None:
                speckle_mesh["renderMaterial"] = material_to_speckle(material)
        submeshes.append(speckle_mesh)           

    return submeshes


def bezier_to_speckle(matrix: List[float], spline: bpy.types.Spline, scale: float, name: Optional[str] = None) -> Curve:
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
        points.extend(
            (
                tuple(matrix @ spline.bezier_points[-1].handle_right * scale),
                tuple(matrix @ spline.bezier_points[0].handle_left * scale),
                tuple(matrix @ spline.bezier_points[0].co * scale),
            )
        )
    
    num_points = len(points)

    flattend_points = []
    for row in points: flattend_points.extend(row)

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
        points=flattend_points,
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


def nurbs_to_speckle(matrix: List[float], spline: bpy.types.Spline, scale: float, name: Optional[str] = None) -> Curve:
    knots = make_knots(spline)
    points = [tuple(matrix @ pt.co.xyz * scale) for pt in spline.points]
    degree = spline.order_u - 1

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)

    flattend_points = []
    for row in points: flattend_points.extend(row)

    return Curve(
        name=name,
        degree=degree,
        closed=spline.use_cyclic_u,
        periodic=spline.use_cyclic_u,
        points=flattend_points,
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


def poly_to_speckle(matrix: List[float], spline: bpy.types.Spline, scale: float, name: Optional[str] = None) -> Polyline:
    points = [tuple(matrix @ pt.co.xyz * scale) for pt in spline.points]

    flattend_points = []
    for row in points: flattend_points.extend(row)

    length = spline.calc_length()
    domain = Interval(start=0, end=length, totalChildrenCount=0)
    return Polyline(
        name=name,
        closed=bool(spline.use_cyclic_u),
        value=list(flattend_points),
        length=length,
        domain=domain,
        bbox=Box(area=0.0, volume=0.0),
        area=0,
        units=UNITS,
    )


def icurve_to_speckle(blender_object: Object, data: bpy.types.Curve, scale=1.0) -> Optional[List[Base]]:
    UNITS = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

    if blender_object.type != "CURVE":
        return None

    blender_object = blender_object.evaluated_get(bpy.context.view_layer.depsgraph)

    mat = blender_object.matrix_world

    curves = []

    if data.bevel_mode == "OBJECT" and data.bevel_object != None:
        mesh = mesh_to_speckle(blender_object, blender_object.to_mesh(), scale)
        curves.extend(mesh)

    for spline in data.splines:
        if spline.type == "BEZIER":
            curves.append(bezier_to_speckle(mat, spline, scale, blender_object.name))

        elif spline.type == "NURBS":
            curves.append(nurbs_to_speckle(mat, spline, scale, blender_object.name))

        elif spline.type == "POLY":
            curves.append(poly_to_speckle(mat, spline, scale, blender_object.name))

    return curves


def ngons_to_speckle_polylines(blender_object: Object, data: bpy.types.Mesh, scale=1.0) -> Optional[List[Polyline]]:
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


def material_to_speckle(blender_mat: bpy.types.Material) -> RenderMaterial:
    speckle_mat = RenderMaterial()
    speckle_mat.name = blender_mat.name

    if blender_mat.use_nodes is True and blender_mat.node_tree.nodes.get(
        "Principled BSDF"
    ):
        inputs = blender_mat.node_tree.nodes["Principled BSDF"].inputs
        speckle_mat.diffuse = to_argb_int(inputs["Base Color"].default_value)
        speckle_mat.emissive = to_argb_int(inputs["Emission"].default_value)
        speckle_mat.roughness = inputs["Roughness"].default_value
        speckle_mat.metalness = inputs["Metallic"].default_value
        speckle_mat.opacity = inputs["Alpha"].default_value

    else:
        speckle_mat.diffuse = to_argb_int(blender_mat.diffuse_color)
        speckle_mat.metalness = blender_mat.metallic
        speckle_mat.roughness = blender_mat.roughness

    return speckle_mat


def material_to_speckle_old(blender_object: Object) -> Optional[RenderMaterial]:
    """Create and return a render material from a blender object"""
    if not getattr(blender_object.data, "materials", None):
        return None

    blender_mat: bpy.types.Material = blender_object.data.materials[0]
    if not blender_mat:
        return None

    return material_to_speckle(blender_mat)


def transform_to_speckle(blender_transform: Iterable[Iterable[float]], scale=1.0) -> Transform:
    value = [y for x in blender_transform for y in x]
    # scale the translation
    for i in (3, 7, 11):
        value[i] *= scale

    return Transform(value=value, units=UNITS)


def block_def_to_speckle(blender_definition: bpy.types.Collection, scale=1.0) -> BlockDefinition:
    geometry = []
    for geo in blender_definition.objects:
        geometry.extend(convert_to_speckle(geo, scale, UNITS, None))
    block_def = BlockDefinition(
        units=UNITS,
        name=blender_definition.name,
        geometry=geometry,
        basePoint=Point(units=UNITS),
    )
    blender_props = get_blender_custom_properties(blender_definition)
    block_def.applicationId = blender_props.pop("applicationId", None)
    return block_def


def block_instance_to_speckle(blender_instance: Object, scale=1.0) -> BlockInstance:
    return BlockInstance(
        blockDefinition=block_def_to_speckle(
            blender_instance.instance_collection, scale
        ),
        transform=transform_to_speckle(blender_instance.matrix_world),
        name=blender_instance.name,
        units=UNITS,
    )


def empty_to_speckle(blender_object: Object, scale=1.0) -> Optional[BlockInstance]:
    # probably an instance collection (block) so let's try it
    try:
        geo = blender_object.instance_collection.objects.items()
        return block_instance_to_speckle(blender_object, scale)
    except AttributeError as err:
        _report(
            f"No instance collection found in empty. Skipping object {blender_object.name}"
        )
        return None
