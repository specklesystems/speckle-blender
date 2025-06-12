from typing import Any, Iterable, List, Optional, Tuple, Dict
from specklepy.objects import Base
from specklepy.objects import DataObject
from specklepy.objects.geometry import (
    Line,
    Polyline,
    Mesh,
    Arc,
    Circle,
    Ellipse,
    Curve,
    Polycurve,
    Point,
)
from specklepy.objects.proxies import InstanceProxy
from specklepy.objects.models.units import (
    get_units_from_string,
    get_scale_factor_to_meters,
)
import bpy
from bpy.types import Object
import mathutils
from ..converter.utils import create_material_from_proxy, find_object_by_id

# Display value property aliases to check for
DISPLAY_VALUE_PROPERTY_ALIASES = [
    "displayValue",
    "displayvalue",
    "@displayValue",
    "display_value",
]

# Element property aliases for collections of objects
ELEMENTS_PROPERTY_ALIASES = [
    "elements",
    "@elements",
]


def get_scale_factor(speckle_object: Base, fallback: float = 1.0) -> float:
    """
    Determines the correct scale factor based on object units
    """
    scale = fallback

    if hasattr(speckle_object, "units") and speckle_object.units:
        # Get scale factor to convert from object units to meters
        unit_scale = get_scale_factor_to_meters(
            get_units_from_string(speckle_object.units)
        )

        blender_unit_scale = bpy.context.scene.unit_settings.scale_length

        scale = unit_scale / blender_unit_scale

    return scale


def generate_unique_name(speckle_object: Base) -> Tuple[str, str]:
    """
    generates unique name for converted blender objects and data-blocks
    """
    # Check if speckle object is a data object
    # Since every data object has name, use it in naming
    # If not extract base name from speckle type itself
    if isinstance(speckle_object, DataObject) and speckle_object.name:
        base_name = speckle_object.name
    else:
        parts = speckle_object.speckle_type.split(".")
        base_name = parts[-1]

    speckle_id = speckle_object.id

    # Define object name - should be simple
    object_name = base_name

    # Define data-block name - should include ID
    datablock_name = f"{base_name}.{speckle_id}"

    return object_name, datablock_name


def convert_to_native(
    speckle_object: Base,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
    definition_collections: Optional[Dict[str, bpy.types.Collection]] = None,
    root_collection: Optional[bpy.types.Collection] = None,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> Optional[Object]:
    """
    converts a speckle object to blender object with material support
    """
    # Determine scale factor based on object units
    scale = get_scale_factor(speckle_object)

    object_name, data_block_name = generate_unique_name(speckle_object)

    converted_object = None

    if material_mapping is None:
        material_mapping = {}

    # first check for render material proxies in the root object
    if hasattr(speckle_object, "renderMaterialProxies"):
        render_materials = render_material_proxy_to_native(speckle_object)
        material_mapping.update(render_materials)

    # Try direct conversion based on object type
    if isinstance(speckle_object, InstanceProxy):
        if definition_collections:
            for def_id, coll in definition_collections.items():
                if def_id == speckle_object.definitionId:
                    if instance_loading_mode == "LINKED_DUPLICATES":
                        converted_object = instance_proxy_to_linked_duplicates(
                            speckle_object, coll, root_collection, scale
                        )
                    else:  # INSTANCE_PROXIES (default)
                        converted_object = instance_proxy_to_native(
                            speckle_object, coll, root_collection, scale
                        )
        else:
            print("No InstanceDefinitionProxy is found.")
    elif isinstance(speckle_object, Line):
        converted_object = line_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Polyline):
        converted_object = polyline_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Arc):
        converted_object = arc_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Circle):
        converted_object = circle_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Ellipse):
        converted_object = ellipse_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Mesh):
        converted_object = mesh_to_native(
            speckle_object, object_name, data_block_name, scale, material_mapping
        )
    elif isinstance(speckle_object, Curve):
        converted_object = curve_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Polycurve):
        converted_object = polycurve_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Point):
        converted_object = point_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    else:
        # Fallback to display value if direct conversion not supported
        mesh, children = display_value_to_native(
            speckle_object, object_name, data_block_name, scale, material_mapping
        )
        if mesh:
            # Create a mesh object with the object_name (simple name) and mesh data
            mesh_obj = bpy.data.objects.new(object_name, mesh)
            converted_object = mesh_obj

            # Parent any child objects to this mesh object
            for child in children:
                child.parent = mesh_obj
        elif children:
            # If we only have non-mesh objects, return the first one as the main object
            converted_object = children[0]

            # Ensure the converted object has the correct name (especially for DataObjects)
            if isinstance(speckle_object, DataObject):
                converted_object.name = object_name
                data_block_name = converted_object.data.name

            # If there are multiple objects, parent remaining ones to the first
            for child in children[1:]:
                child.parent = converted_object

    if converted_object:
        # Store Speckle ID in custom property
        converted_object["speckle_id"] = speckle_object.id
        if hasattr(speckle_object, "applicationId"):
            converted_object["speckle_application_id"] = speckle_object.applicationId

    return converted_object


def display_value_to_native(
    speckle_object: Base,
    object_name: str,
    data_block_name: str,
    scale: float,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> Tuple[Optional[bpy.types.Mesh], List[Object]]:
    """
    fallback conversion mechanism using displayValue if present
    """
    # Before calling _members_to_native, check if the parent object has an applicationId
    has_app_id = (
        hasattr(speckle_object, "applicationId") and speckle_object.applicationId
    )
    parent_app_id = speckle_object.applicationId if has_app_id else None

    mesh, children = _members_to_native(
        speckle_object,
        object_name,
        data_block_name,
        scale,
        DISPLAY_VALUE_PROPERTY_ALIASES,
        True,
        material_mapping,
    )

    # If the parent had an applicationId and we created a mesh, apply the material
    if (
        parent_app_id
        and mesh
        and material_mapping
        and parent_app_id in material_mapping
    ):
        material = material_mapping[parent_app_id]
        mesh.materials.append(material)

    # For each child object, check if it needs material from parent
    for child in children:
        if parent_app_id and material_mapping and parent_app_id in material_mapping:
            if (
                hasattr(child, "data")
                and hasattr(child.data, "materials")
                and len(child.data.materials) == 0
            ):
                material = material_mapping[parent_app_id]
                child.data.materials.append(material)

    return mesh, children


def elements_to_native(
    speckle_object: Base,
    object_name: str,
    data_block_name: str,
    scale: float,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> List[Object]:
    """
    convert elements collection of a speckle object
    """
    (_, elements) = _members_to_native(
        speckle_object,
        object_name,
        data_block_name,
        scale,
        ELEMENTS_PROPERTY_ALIASES,
        False,
        material_mapping,
    )
    return elements


def _members_to_native(
    speckle_object: Base,
    object_name: str,
    data_block_name: str,
    scale: float,
    members: Iterable[str],
    combineMeshes: bool,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> Tuple[Optional[bpy.types.Mesh], List[Object]]:
    """
    converts a given speckle_object by converting specified members
    """
    meshes: List[Mesh] = []
    others: List[Base] = []

    for alias in members:
        display = getattr(speckle_object, alias, None)

        count = 0
        MAX_DEPTH = 255  # some large value, to prevent infinite recursion

        def separate(value: Any) -> bool:
            nonlocal meshes, others, count, MAX_DEPTH

            if combineMeshes and isinstance(value, Mesh):
                meshes.append(value)
            elif isinstance(value, Base):
                others.append(value)
            elif isinstance(value, list):
                count += 1
                if count > MAX_DEPTH:
                    return True
                for x in value:
                    separate(x)

            return False

        did_halt = separate(display)

        if did_halt:
            print(
                f"Traversal of {speckle_object.speckle_type} {speckle_object.id} halted after traversal depth exceeds MAX_DEPTH={MAX_DEPTH}. Are there circular references in object structure?"
            )

    children: List[Object] = []
    mesh = None

    if meshes:
        mesh = meshes_to_native(
            speckle_object, meshes, data_block_name, scale, material_mapping
        )

    # Check if the original object is a DataObject
    is_data_object = isinstance(speckle_object, DataObject)

    for item in others:
        try:
            blender_object = convert_to_native(item, material_mapping, instance_loading_mode="INSTANCE_PROXIES")
            if blender_object:
                # If the parent is a DataObject, override the name of the converted child
                if is_data_object:
                    blender_object.name = object_name
                    data_block_name = blender_object.data.name
                children.append(blender_object)
        except Exception as ex:
            print(f"Failed to convert display value {item}: {ex}")

    return (mesh, children)


def line_to_native(
    speckle_line: Line, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a speckle line to a blender curve
    """
    if not speckle_line.start or not speckle_line.end:
        raise ValueError("Line is missing start or end point")

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    spline = curve.splines.new("POLY")
    spline.points.add(1)

    spline.points[0].co = (
        float(speckle_line.start.x) * scale,
        float(speckle_line.start.y) * scale,
        float(speckle_line.start.z) * scale,
        1.0,
    )

    spline.points[1].co = (
        float(speckle_line.end.x) * scale,
        float(speckle_line.end.y) * scale,
        float(speckle_line.end.z) * scale,
        1.0,
    )

    curve_obj = bpy.data.objects.new(object_name, curve)

    return curve_obj


def polyline_to_native(
    speckle_polyline: Polyline,
    object_name: str,
    data_block_name: str,
    scale: float = 1.0,
) -> Object:
    """
    converts a speckle polyline to blender curve
    """
    if not speckle_polyline.value or len(speckle_polyline.value) < 6:
        raise ValueError("Polyline must have at least two points")

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    spline = curve.splines.new("POLY")

    num_points = len(speckle_polyline.value) // 3  # divide by 3 to get point count

    # Add the required number of points to the spline
    if num_points > 1:
        spline.points.add(num_points - 1)

    for i in range(num_points):
        # Note: Blender curve points are 4D (x, y, z, w) where w is weight
        spline.points[i].co = (
            float(speckle_polyline.value[i * 3]) * scale,
            float(speckle_polyline.value[i * 3 + 1]) * scale,
            float(speckle_polyline.value[i * 3 + 2]) * scale,
            1.0,
        )

    if hasattr(speckle_polyline, "closed") and speckle_polyline.closed:
        spline.use_cyclic_u = True

    curve_obj = bpy.data.objects.new(object_name, curve)

    return curve_obj


def mesh_to_native(
    speckle_mesh: Mesh,
    object_name: str,
    data_block_name: str,
    scale: float = 1.0,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> Object:
    """
    converts a speckle mesh to a blender mesh with material support
    """
    mesh = mesh_to_native_mesh(speckle_mesh, data_block_name, scale)

    mesh_obj = bpy.data.objects.new(object_name, mesh)

    # Add vertex colors if available
    if hasattr(speckle_mesh, "colors") and len(speckle_mesh.colors) > 0:
        add_vertex_colors(mesh, speckle_mesh.colors)

    # Add texture coordinates if available
    if (
        hasattr(speckle_mesh, "textureCoordinates")
        and len(speckle_mesh.textureCoordinates) > 0
    ):
        add_texture_coordinates(mesh, speckle_mesh.textureCoordinates)

    # Apply material if available in mapping
    if material_mapping and hasattr(speckle_mesh, "applicationId"):
        app_id = speckle_mesh.applicationId
        if app_id in material_mapping:
            material = material_mapping[app_id]
            mesh.materials.append(material)

    return mesh_obj


def mesh_to_native_mesh(
    speckle_mesh: Mesh, name: str, scale: float = 1.0
) -> bpy.types.Mesh:
    """
    converts a single Speckle mesh to a Blender mesh object
    """
    return meshes_to_native(speckle_mesh, [speckle_mesh], name, scale)


def meshes_to_native(
    speckle_object: Base,
    meshes: List[Mesh],
    name: str,
    scale: float,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> bpy.types.Mesh:
    """
    combines multiple Speckle meshes into a single Blender mesh with material support
    """
    blender_mesh = bpy.data.meshes.new(name)

    mesh_face_ranges: List[
        Tuple[int, int, int]
    ] = []  # List of (start_face, end_face, mesh_index)
    current_face = 0

    mesh_materials: Dict[int, bpy.types.Material] = {}  # Maps mesh index to material

    has_normals = any(
        hasattr(m, "vertexNormals") and len(m.vertexNormals) > 0 for m in meshes
    )

    all_vertices: List[Tuple[float, float, float]] = []
    all_faces: List[List[float]] = []
    all_normals: Optional[List[List[float]]] = [] if has_normals else None

    vertex_offset = 0

    for mesh_idx, mesh in enumerate(meshes):
        start_face = current_face

        # check if we have a material for this mesh
        if material_mapping and hasattr(mesh, "applicationId"):
            app_id = mesh.applicationId
            if app_id in material_mapping:
                mesh_materials[mesh_idx] = material_mapping[app_id]

        # Add vertices with scale applied
        for i in range(0, len(mesh.vertices), 3):
            all_vertices.append(
                (
                    float(mesh.vertices[i]) * scale,
                    float(mesh.vertices[i + 1]) * scale,
                    float(mesh.vertices[i + 2]) * scale,
                )
            )

        # Add faces
        i = 0
        face_count = 0
        while i < len(mesh.faces):
            vertex_count = mesh.faces[i]
            face: List[float] = []
            for j in range(1, vertex_count + 1):
                vertex_index = mesh.faces[i + j]
                face.append(vertex_index + vertex_offset)

                ii = vertex_index * 3

                if all_normals is not None:
                    if hasattr(mesh, "vertexNormals") and len(mesh.vertexNormals) > 0:
                        all_normals.append(
                            [
                                mesh.vertexNormals[ii],
                                mesh.vertexNormals[ii + 1],
                                mesh.vertexNormals[ii + 2],
                            ]
                        )
                    else:
                        all_normals.append(
                            (0, 0, 0)
                        )  # Zero vector is treated as auto normal

            all_faces.append(face)

            i += vertex_count + 1
            face_count += 1
            current_face += 1

        vertex_offset += len(mesh.vertices) // 3

        # Store face range if this mesh has faces
        if face_count > 0:
            mesh_face_ranges.append((start_face, current_face - 1, mesh_idx))

    blender_mesh.from_pydata(all_vertices, [], all_faces)
    blender_mesh.update()

    # Set normals
    if all_normals is not None:
        blender_mesh.normals_split_custom_set(all_normals)
    else:
        blender_mesh.shade_smooth()

    # If we have materials, add them to the mesh
    if mesh_materials:
        materials_added = set()
        material_indices = {}  # Maps material name to index in the mesh

        # first add all unique materials
        for mesh_idx, material in mesh_materials.items():
            if material.name not in materials_added:
                blender_mesh.materials.append(material)
                material_indices[material.name] = len(blender_mesh.materials) - 1
                materials_added.add(material.name)

        # then assign material indices to faces
        for start_face, end_face, mesh_idx in mesh_face_ranges:
            if mesh_idx in mesh_materials:
                material = mesh_materials[mesh_idx]
                material_index = material_indices[material.name]

                for face_idx in range(start_face, end_face + 1):
                    if face_idx < len(blender_mesh.polygons):
                        blender_mesh.polygons[face_idx].material_index = material_index

    return blender_mesh


def add_vertex_colors(blender_mesh: bpy.types.Mesh, colors: List[int]) -> None:
    """
    add vertex colors to a Blender mesh
    """
    if not blender_mesh.vertices or len(colors) < len(blender_mesh.vertices) * 4:
        return

    # Create a new vertex color layer
    if not blender_mesh.vertex_colors:
        blender_mesh.vertex_colors.new()

    color_layer = blender_mesh.vertex_colors.active

    # Set vertex colors for each loop
    for poly in blender_mesh.polygons:
        for loop_idx in poly.loop_indices:
            vertex_idx = blender_mesh.loops[loop_idx].vertex_index
            color_idx = vertex_idx * 4

            # RGBA values normalized to 0.0-1.0 range
            r = colors[color_idx] / 255.0
            g = colors[color_idx + 1] / 255.0
            b = colors[color_idx + 2] / 255.0
            a = colors[color_idx + 3] / 255.0

            color_layer.data[loop_idx].color = (r, g, b, a)


def add_texture_coordinates(
    blender_mesh: bpy.types.Mesh, tex_coords: List[float]
) -> None:
    """
    add texture coordinates to a Blender mesh
    """
    if not blender_mesh.vertices or len(tex_coords) < len(blender_mesh.vertices) * 2:
        return

    if not blender_mesh.uv_layers:
        blender_mesh.uv_layers.new()

    uv_layer = blender_mesh.uv_layers.active

    for poly in blender_mesh.polygons:
        for loop_idx in poly.loop_indices:
            vertex_idx = blender_mesh.loops[loop_idx].vertex_index
            uv_idx = vertex_idx * 2

            u = tex_coords[uv_idx]
            v = tex_coords[uv_idx + 1]

            uv_layer.data[loop_idx].uv = (u, v)


def render_material_proxy_to_native(
    speckle_object: Base,
) -> Dict[str, bpy.types.Material]:
    """
    converts RenderMaterialProxies to Blender materials and maintains a mapping
    of applicationId to material.
    """
    assigned_objects = {}

    # check if object has renderMaterialProxies
    if not hasattr(speckle_object, "renderMaterialProxies"):
        print("No render material proxies found!")
        return assigned_objects

    # process each render material proxy
    for proxy in speckle_object.renderMaterialProxies:
        if not hasattr(proxy, "value") or not hasattr(proxy, "objects"):
            print("Render material proxy has no value or no object has been assigned!")
            continue

        render_material = proxy.value
        material_name = getattr(render_material, "name", "Material")

        # create or get existing material
        blender_material = create_material_from_proxy(render_material, material_name)

        # assign material to objects by applicationId
        for applicationId in proxy.objects:
            assigned_objects[applicationId] = blender_material

    return assigned_objects


def arc_to_native(
    speckle_arc: Arc, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a Speckle arc to a Blender NURBS curve.
    """
    import math
    import mathutils

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    plane = speckle_arc.plane
    if not plane:
        raise ValueError("Arc is missing plane")

    start_point = mathutils.Vector(
        (
            float(speckle_arc.startPoint.x) * scale,
            float(speckle_arc.startPoint.y) * scale,
            float(speckle_arc.startPoint.z) * scale,
        )
    )

    mid_point = mathutils.Vector(
        (
            float(speckle_arc.midPoint.x) * scale,
            float(speckle_arc.midPoint.y) * scale,
            float(speckle_arc.midPoint.z) * scale,
        )
    )

    end_point = mathutils.Vector(
        (
            float(speckle_arc.endPoint.x) * scale,
            float(speckle_arc.endPoint.y) * scale,
            float(speckle_arc.endPoint.z) * scale,
        )
    )

    center = mathutils.Vector(
        (
            float(plane.origin.x) * scale,
            float(plane.origin.y) * scale,
            float(plane.origin.z) * scale,
        )
    )

    radius = (start_point - center).length

    normal = mathutils.Vector(
        (
            float(plane.normal.x),
            float(plane.normal.y),
            float(plane.normal.z),
        )
    )
    normal.normalize()

    x_dir = mathutils.Vector(
        (
            float(plane.xdir.x),
            float(plane.xdir.y),
            float(plane.xdir.z),
        )
    )
    x_dir.normalize()

    y_dir = mathutils.Vector(
        (
            float(plane.ydir.x),
            float(plane.ydir.y),
            float(plane.ydir.z),
        )
    )
    y_dir.normalize()

    # convert global coordinates to local plane coordinates for angle calculation
    def to_local_coords(point):
        v = point - center
        x = v.dot(x_dir)
        y = v.dot(y_dir)
        return x, y

    start_local_x, start_local_y = to_local_coords(start_point)
    mid_local_x, mid_local_y = to_local_coords(mid_point)
    end_local_x, end_local_y = to_local_coords(end_point)

    start_angle = math.atan2(start_local_y, start_local_x)
    mid_angle = math.atan2(mid_local_y, mid_local_x)
    end_angle = math.atan2(end_local_y, end_local_x)

    sweep_angle = end_angle - start_angle

    if sweep_angle > math.pi:
        sweep_angle -= 2 * math.pi
    elif sweep_angle < -math.pi:
        sweep_angle += 2 * math.pi

    mid_angle_rel = (mid_angle - start_angle) % (2 * math.pi)

    mid_expected = sweep_angle / 2.0
    if abs((mid_angle_rel - mid_expected + math.pi) % (2 * math.pi) - math.pi) > 0.1:
        if sweep_angle > 0:
            sweep_angle -= 2 * math.pi
        else:
            sweep_angle += 2 * math.pi

    spline = curve.splines.new("NURBS")
    spline.use_cyclic_u = False

    Ndiv = max(int(abs(sweep_angle / 0.3)), 4)
    step = sweep_angle / float(Ndiv)

    spline.points.add(Ndiv)

    for i in range(Ndiv + 1):
        angle = start_angle + step * i
        local_x = math.cos(angle) * radius
        local_y = math.sin(angle) * radius

        # Convert back to global coordinates
        point = center + x_dir * local_x + y_dir * local_y
        spline.points[i].co = (point.x, point.y, point.z, 1.0)  # 1.0 is the weight

    spline.use_endpoint_u = True
    spline.order_u = 3
    spline.resolution_u = 12

    curve_obj = bpy.data.objects.new(object_name, curve)

    return curve_obj


def circle_to_native(
    speckle_circle: Circle, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a Speckle circle to a Blender NURBS curve.
    """
    import math
    import mathutils

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    center = mathutils.Vector(
        (
            float(speckle_circle.plane.origin.x) * scale,
            float(speckle_circle.plane.origin.y) * scale,
            float(speckle_circle.plane.origin.z) * scale,
        )
    )

    radius = float(speckle_circle.radius) * scale

    normal = mathutils.Vector(
        (
            float(speckle_circle.plane.normal.x),
            float(speckle_circle.plane.normal.y),
            float(speckle_circle.plane.normal.z),
        )
    )
    normal.normalize()

    x_axis = mathutils.Vector(
        (
            float(speckle_circle.plane.xdir.x),
            float(speckle_circle.plane.xdir.y),
            float(speckle_circle.plane.xdir.z),
        )
    )
    x_axis.normalize()

    y_axis = mathutils.Vector(
        (
            float(speckle_circle.plane.ydir.x),
            float(speckle_circle.plane.ydir.y),
            float(speckle_circle.plane.ydir.z),
        )
    )
    y_axis.normalize()

    spline = curve.splines.new("NURBS")

    # number of points for the circle
    num_points = 16  # set it to 16 as default - looks smooth
    spline.points.add(num_points - 1)  # -1 because it already has one point

    for i in range(num_points):
        angle = 2 * math.pi * i / num_points

        point = (
            center
            + x_axis * (radius * math.cos(angle))
            + y_axis * (radius * math.sin(angle))
        )

        spline.points[i].co = (point.x, point.y, point.z, 1.0)  # 1.0 is the weight

    spline.use_cyclic_u = True

    spline.order_u = 4
    spline.resolution_u = 12

    curve_obj = bpy.data.objects.new(object_name, curve)

    return curve_obj


def ellipse_to_native(
    speckle_ellipse: Ellipse, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a Speckle ellipse to a Blender NURBS curve.
    """
    import mathutils

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    center = mathutils.Vector(
        (
            float(speckle_ellipse.plane.origin.x) * scale,
            float(speckle_ellipse.plane.origin.y) * scale,
            float(speckle_ellipse.plane.origin.z) * scale,
        )
    )

    radius_x = float(speckle_ellipse.firstRadius) * scale
    radius_y = float(speckle_ellipse.secondRadius) * scale

    normal = mathutils.Vector(
        (
            float(speckle_ellipse.plane.normal.x),
            float(speckle_ellipse.plane.normal.y),
            float(speckle_ellipse.plane.normal.z),
        )
    )
    normal.normalize()

    # get orientation vectors from plane
    x_axis = mathutils.Vector(
        (
            float(speckle_ellipse.plane.xdir.x),
            float(speckle_ellipse.plane.xdir.y),
            float(speckle_ellipse.plane.xdir.z),
        )
    )
    x_axis.normalize()

    y_axis = mathutils.Vector(
        (
            float(speckle_ellipse.plane.ydir.x),
            float(speckle_ellipse.plane.ydir.y),
            float(speckle_ellipse.plane.ydir.z),
        )
    )
    y_axis.normalize()

    spline = curve.splines.new("BEZIER")

    # an ellipse can be nicely represented with 4 Bezier segments
    spline.bezier_points.add(3)  # add 3 more for a total of 4 points

    # control point factor
    cp_factor = 0.5522847498307936  # (4/3)*tan(pi/8)

    # point 1 (positive x-axis)
    spline.bezier_points[0].co = center + x_axis * radius_x
    spline.bezier_points[0].handle_left = (
        center + x_axis * radius_x - y_axis * radius_y * cp_factor
    )
    spline.bezier_points[0].handle_right = (
        center + x_axis * radius_x + y_axis * radius_y * cp_factor
    )

    # point 2 (positive y-axis)
    spline.bezier_points[1].co = center + y_axis * radius_y
    spline.bezier_points[1].handle_left = (
        center + y_axis * radius_y - x_axis * radius_x * cp_factor
    )
    spline.bezier_points[1].handle_right = (
        center + y_axis * radius_y + x_axis * radius_x * cp_factor
    )

    # point 3 (negative x-axis)
    spline.bezier_points[2].co = center - x_axis * radius_x
    spline.bezier_points[2].handle_left = (
        center - x_axis * radius_x + y_axis * radius_y * cp_factor
    )
    spline.bezier_points[2].handle_right = (
        center - x_axis * radius_x - y_axis * radius_y * cp_factor
    )

    # point 4 (negative y-axis)
    spline.bezier_points[3].co = center - y_axis * radius_y
    spline.bezier_points[3].handle_left = (
        center - y_axis * radius_y + x_axis * radius_x * cp_factor
    )
    spline.bezier_points[3].handle_right = (
        center - y_axis * radius_y - x_axis * radius_x * cp_factor
    )

    spline.use_cyclic_u = True

    curve_obj = bpy.data.objects.new(object_name, curve)

    return curve_obj


def curve_to_native(
    speckle_curve: Curve, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a speckle NURBS curve to a blender curve object
    """
    if not isinstance(speckle_curve, Curve):
        raise TypeError("Expected a Speckle Curve object.")

    # fallback for degree 2 curves: use displayValue if available
    if (
        getattr(speckle_curve, "degree", None) == 2
        and hasattr(speckle_curve, "displayValue")
        and speckle_curve.displayValue
    ):
        print("curve_to_native: degree 2 curve, falling back to displayValue")
        mesh, children = display_value_to_native(
            speckle_curve, object_name, data_block_name, scale
        )
        if mesh:
            curve_obj = bpy.data.objects.new(object_name, mesh)
            return curve_obj
        elif children:
            return children[0]
        else:
            return None

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    spline = curve.splines.new("NURBS")

    points = speckle_curve.points
    if isinstance(points, list) and len(points) == 1 and hasattr(points[0], "data"):
        points = points[0].data

    weights = getattr(speckle_curve, "weights", None)
    if isinstance(weights, list) and len(weights) == 1 and hasattr(weights[0], "data"):
        weights = weights[0].data

    point_count = len(points) // 3

    if (
        speckle_curve.closed
        and speckle_curve.degree > 2
        and point_count > speckle_curve.degree
    ):
        point_count = point_count - speckle_curve.degree

    if point_count > 1:
        spline.points.add(point_count - 1)

    for i in range(point_count):
        x = float(points[i * 3]) * scale
        y = float(points[i * 3 + 1]) * scale
        z = float(points[i * 3 + 2]) * scale

        w = 1.0
        if weights and i < len(weights):
            w = float(weights[i])

        print(f"curve_to_native: point {i}: ({x}, {y}, {z}, {w})")
        spline.points[i].co = (x, y, z, w)

    spline.use_cyclic_u = speckle_curve.closed
    spline.use_endpoint_u = not speckle_curve.periodic
    spline.order_u = speckle_curve.degree + 1
    spline.resolution_u = 12

    curve_obj = bpy.data.objects.new(object_name, curve)
    return curve_obj


def polycurve_to_native(
    speckle_polycurve: Polycurve,
    object_name: str,
    data_block_name: str,
    scale: float = 1.0,
) -> Optional[Object]:
    """
    converts a speckle polycurve to a Blender curve object.
    """
    if not hasattr(speckle_polycurve, "segments") or not speckle_polycurve.segments:
        # fallback to displayValue if no segments - not sure if it ever happens
        if (
            hasattr(speckle_polycurve, "displayValue")
            and speckle_polycurve.displayValue
        ):
            mesh, children = display_value_to_native(
                speckle_polycurve, object_name, data_block_name, scale
            )
            if mesh:
                curve_obj = bpy.data.objects.new(object_name, mesh)
                return curve_obj
            elif children:
                return children[0]
            else:
                return None
        raise ValueError("Polycurve is missing segments and has no displayValue")

    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    for idx, segment in enumerate(speckle_polycurve.segments):
        temp_curve = bpy.data.curves.new(f"temp_curve_{idx}", type="CURVE")
        temp_curve.dimensions = "3D"
        temp_obj = None

        # convert the segment using the appropriate function
        if isinstance(segment, Line):
            temp_obj = line_to_native(
                segment, f"temp_line_{idx}", f"temp_line_data_{idx}", scale
            )
        elif isinstance(segment, Polyline):
            temp_obj = polyline_to_native(
                segment, f"temp_polyline_{idx}", f"temp_polyline_data_{idx}", scale
            )
        elif isinstance(segment, Arc):
            temp_obj = arc_to_native(
                segment, f"temp_arc_{idx}", f"temp_arc_data_{idx}", scale
            )
        elif isinstance(segment, Circle):
            temp_obj = circle_to_native(
                segment, f"temp_circle_{idx}", f"temp_circle_data_{idx}", scale
            )
        elif isinstance(segment, Ellipse):
            temp_obj = ellipse_to_native(
                segment, f"temp_ellipse_{idx}", f"temp_ellipse_data_{idx}", scale
            )
        elif isinstance(segment, Curve):
            temp_obj = curve_to_native(
                segment, f"temp_curve_{idx}", f"temp_curve_data_{idx}", scale
            )
        else:
            bpy.data.curves.remove(temp_curve)
            raise ValueError(f"Unsupported curve segment type: {type(segment)}")

        # copy splines from temp_obj to main curve
        if temp_obj and temp_obj.data and hasattr(temp_obj.data, "splines"):
            for src_spline in temp_obj.data.splines:
                dst_spline = curve.splines.new(src_spline.type)
                if src_spline.type == "BEZIER":
                    dst_spline.bezier_points.add(len(src_spline.bezier_points) - 1)
                    for i, bp in enumerate(src_spline.bezier_points):
                        dst_spline.bezier_points[i].co = bp.co
                        dst_spline.bezier_points[i].handle_left = bp.handle_left
                        dst_spline.bezier_points[i].handle_right = bp.handle_right
                else:
                    dst_spline.points.add(len(src_spline.points) - 1)
                    for i, point in enumerate(src_spline.points):
                        dst_spline.points[i].co = point.co
                dst_spline.use_cyclic_u = src_spline.use_cyclic_u
                if hasattr(src_spline, "order_u"):
                    dst_spline.order_u = src_spline.order_u
                if hasattr(src_spline, "resolution_u"):
                    dst_spline.resolution_u = 12
                if hasattr(src_spline, "use_endpoint_u"):
                    dst_spline.use_endpoint_u = True
            bpy.data.objects.remove(temp_obj)
        else:
            raise ValueError(f"Failed to convert segment of type {type(segment)}")

        bpy.data.curves.remove(temp_curve)

    curve_obj = bpy.data.objects.new(object_name, curve)
    return curve_obj


def point_to_native(
    speckle_point: Point, object_name: str, data_block_name: str, scale: float = 1.0
) -> bpy.types.Object:
    """
    converts a speckle point to a blender empty object of type 'PLAIN_AXES'
    """
    point_obj = bpy.data.objects.new(object_name, None)

    point_obj.empty_display_type = "PLAIN_AXES"
    point_obj.empty_display_size = 0.1  # default size

    point_obj.location = (
        float(speckle_point.x) * scale,
        float(speckle_point.y) * scale,
        float(speckle_point.z) * scale,
    )

    return point_obj


def find_instance_definitions(root_object: Base) -> Dict[str, Base]:
    """
    finds all instance definitions in the root object
    """
    definitions = {}

    definitions_attr_names = [
        "instanceDefinitionProxies",
        "@instanceDefinitionProxies",
        "instanceDefinitions",
        "@instanceDefinitions",
    ]

    for attr_name in definitions_attr_names:
        if hasattr(root_object, attr_name):
            attr_value = getattr(root_object, attr_name)
            if isinstance(attr_value, list):
                for definition in attr_value:
                    if hasattr(definition, "applicationId"):
                        definitions[definition.applicationId] = definition

    if not definitions:
        print("No instanceDefinitionProxy founded!")

    return definitions


def sort_instance_components(definitions, instances):
    """
    sort instance components by max depth and type (definitions first)
    """
    components = []

    # Add definitions with their max_depth
    for def_id, definition in definitions.items():
        max_depth = getattr(definition, "maxDepth", 0)
        components.append((max_depth, 0, def_id, definition))

    for instance in instances:
        if hasattr(instance, "definitionId") and instance.definitionId in definitions:
            definition = definitions[instance.definitionId]
            max_depth = getattr(definition, "maxDepth", 0)
            components.append((max_depth, 1, instance.id, instance))

    components.sort(key=lambda x: (-x[0], x[1]))
    return components


def instance_definition_proxy_to_native(
    root_object: Base,
    material_mapping: Dict[str, Any],
    processed_definitions: Dict[str, Any] = None,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> Tuple[Dict[str, bpy.types.Collection], Dict[str, Any]]:
    """
    converts instance definition proxies to Blender collections recursively
    """
    # Validate instance loading mode
    assert instance_loading_mode in ["INSTANCE_PROXIES", "LINKED_DUPLICATES"], (
        f"Invalid instance_loading_mode: {instance_loading_mode}. "
        "Must be 'INSTANCE_PROXIES' or 'LINKED_DUPLICATES'"
    )
    assert isinstance(material_mapping, dict), "material_mapping must be a dictionary"
    
    processed_definitions = processed_definitions or {}
    definition_collections = {}
    converted_objects = {}
    definitions = find_instance_definitions(root_object)

    if not definitions:
        print("No definitions found!")
        return definition_collections, converted_objects

    existing_definitions = bpy.data.collections.get("InstanceDefinitions")
    if existing_definitions:
        for coll in existing_definitions.children:
            for obj in coll.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(coll, do_unlink=True)
        bpy.data.collections.remove(existing_definitions, do_unlink=True)

    sorted_components = sort_instance_components(definitions, [])

    for _, _, def_id, definition in sorted_components:
        collection_name = getattr(definition, "name", f"Definition_{def_id[:8]}")

        if def_id in processed_definitions:
            definition_collections[def_id] = processed_definitions[def_id]
            continue

        definition_collection = bpy.data.collections.new(collection_name)
        definition_collections[def_id] = definition_collection

        # Store metadata
        definition_collection["speckle_id"] = def_id
        definition_collection["speckle_type"] = getattr(
            definition, "speckle_type", "InstanceDefinitionProxy"
        )
        if hasattr(definition, "maxDepth"):
            definition_collection["max_depth"] = definition.maxDepth

        # Process objects, including nested instances
        if hasattr(definition, "objects") and isinstance(definition.objects, list):
            for obj_id in definition.objects:
                found_obj = find_object_by_id(root_object, obj_id)

                if found_obj:
                    try:
                        # Handle nested instance proxies
                        if (
                            isinstance(found_obj, InstanceProxy)
                            and found_obj.definitionId in definitions
                        ):
                            nested_def = definitions[found_obj.definitionId]
                            max_depth = getattr(nested_def, "maxDepth", 0)
                            if max_depth > 0:  # Only process if max_depth allows
                                assert found_obj.definitionId in definition_collections, (
                                    f"Definition collection not found for nested instance {found_obj.definitionId}"
                                )
                                
                                if instance_loading_mode == "LINKED_DUPLICATES":
                                    blender_obj = instance_proxy_to_linked_duplicates(
                                        found_obj,
                                        definition_collections[found_obj.definitionId],
                                        definition_collection,
                                        scale=1.0,
                                    )
                                else:  # INSTANCE_PROXIES (default)
                                    blender_obj = instance_proxy_to_native(
                                        found_obj,
                                        definition_collections[found_obj.definitionId],
                                        definition_collection,
                                        scale=1.0,
                                    )
                                if blender_obj:
                                    converted_objects[obj_id] = blender_obj
                        else:
                            blender_obj = convert_to_native(found_obj, material_mapping, instance_loading_mode="INSTANCE_PROXIES")
                            if blender_obj:
                                definition_collection.objects.link(blender_obj)
                                converted_objects[obj_id] = blender_obj
                                if hasattr(found_obj, "id"):
                                    converted_objects[found_obj.id] = blender_obj
                                if hasattr(found_obj, "applicationId"):
                                    converted_objects[found_obj.applicationId] = (
                                        blender_obj
                                    )
                    except Exception as e:
                        print(f"Error converting object: {str(e)}")
                else:
                    print(f"Failed to find object with ID: {obj_id}")

        processed_definitions[def_id] = definition_collection

    return definition_collections, converted_objects


def proxy_scale(speckle_object: Base, fallback: float = 1.0) -> float:
    """
    determines the correct scale factor based on object units and Blender settings
    """
    unit_settings = bpy.context.scene.unit_settings

    if unit_settings.system != "METRIC":
        original_system = unit_settings.system
        unit_settings.system = "METRIC"
        unit_settings.system = original_system

    blender_scale = unit_settings.scale_length

    unit_scale = 1.0

    if hasattr(speckle_object, "units") and speckle_object.units:
        try:
            # get scale factor to convert from object units to meters
            unit_scale = get_scale_factor_to_meters(
                get_units_from_string(speckle_object.units)
            )
        except Exception as e:
            print(f"[WARNING] Failed to determine unit scale: {str(e)}")
            unit_scale = fallback

    final_scale = unit_scale / blender_scale

    return final_scale


def instance_proxy_to_linked_duplicates(
    speckle_instance: InstanceProxy,
    definition_collection: bpy.types.Collection,
    root_collection: bpy.types.Collection,
    scale: float = 1.0,
) -> Optional[bpy.types.Object]:
    """
    converts a Speckle InstanceProxy to linked duplicate objects
    """
    if not definition_collection:
        print(f"Definition collection not found for instance {speckle_instance.id}")
        return None

    unit_scale = proxy_scale(speckle_instance)

    # convert transformation matrix
    matrix = mathutils.Matrix(
        [
            [
                speckle_instance.transform[0],
                speckle_instance.transform[1],
                speckle_instance.transform[2],
                speckle_instance.transform[3],
            ],
            [
                speckle_instance.transform[4],
                speckle_instance.transform[5],
                speckle_instance.transform[6],
                speckle_instance.transform[7],
            ],
            [
                speckle_instance.transform[8],
                speckle_instance.transform[9],
                speckle_instance.transform[10],
                speckle_instance.transform[11],
            ],
            [
                speckle_instance.transform[12],
                speckle_instance.transform[13],
                speckle_instance.transform[14],
                speckle_instance.transform[15],
            ],
        ]
    )

    location, rotation, scale_vector = matrix.decompose()
    location = location * unit_scale

    # create transformation matrix
    final_matrix = (
        mathutils.Matrix.Translation(location)
        @ rotation.to_matrix().to_4x4()
        @ mathutils.Matrix.Diagonal(scale_vector).to_4x4()
    )

    instance_name = f"Instance_{speckle_instance.id[:8]}"
    parent_empty = bpy.data.objects.new(instance_name, None)
    parent_empty.empty_display_type = 'PLAIN_AXES'
    parent_empty.empty_display_size = 0.1
    
    parent_empty.matrix_world = final_matrix
    
    # link parent to root collection
    root_collection.objects.link(parent_empty)
    
    parent_empty["speckle_id"] = speckle_instance.id
    parent_empty["speckle_type"] = speckle_instance.speckle_type
    parent_empty["definition_id"] = speckle_instance.definitionId
    if hasattr(speckle_instance, "maxDepth"):
        parent_empty["max_depth"] = speckle_instance.maxDepth

    duplicated_objects = []
    for obj in definition_collection.objects:
        # create a copy of the object with linked data
        duplicate_obj = obj.copy()
        
        duplicate_obj.name = f"{obj.name}_{speckle_instance.id[:8]}"
        
        root_collection.objects.link(duplicate_obj)
        
        # apply the instance transformation directly to each object
        duplicate_obj.matrix_world = final_matrix @ obj.matrix_world
        
        duplicated_objects.append(duplicate_obj)

    return parent_empty


def instance_proxy_to_native(
    speckle_instance: InstanceProxy,
    definition_collection: bpy.types.Collection,
    root_collection: bpy.types.Collection,
    scale: float = 1.0,
) -> Optional[bpy.types.Object]:
    """
    converts a Speckle InstanceProxy to Blender collection instance
    """
    if not definition_collection:
        print(f"Definition collection not found for instance {speckle_instance.id}")
        return None

    unit_scale = proxy_scale(speckle_instance)

    # convert transformation matrix
    matrix = mathutils.Matrix(
        [
            [
                speckle_instance.transform[0],
                speckle_instance.transform[1],
                speckle_instance.transform[2],
                speckle_instance.transform[3],
            ],
            [
                speckle_instance.transform[4],
                speckle_instance.transform[5],
                speckle_instance.transform[6],
                speckle_instance.transform[7],
            ],
            [
                speckle_instance.transform[8],
                speckle_instance.transform[9],
                speckle_instance.transform[10],
                speckle_instance.transform[11],
            ],
            [
                speckle_instance.transform[12],
                speckle_instance.transform[13],
                speckle_instance.transform[14],
                speckle_instance.transform[15],
            ],
        ]
    )

    location, rotation, scale_vector = matrix.decompose()

    location = location * unit_scale

    bpy.ops.object.collection_instance_add(
        collection=definition_collection.name,
        align="WORLD",
        location=(0, 0, 0),
        rotation=(0, 0, 0),
        scale=(1, 1, 1),
    )

    instance_obj = bpy.context.active_object

    instance_obj.empty_display_size = 0

    instance_name = f"Instance_{speckle_instance.id[:8]}"
    instance_obj.name = instance_name

    if instance_obj.name not in root_collection.objects:
        for coll in instance_obj.users_collection:
            coll.objects.unlink(instance_obj)
        root_collection.objects.link(instance_obj)

    instance_obj["speckle_id"] = speckle_instance.id
    instance_obj["speckle_type"] = speckle_instance.speckle_type
    instance_obj["definition_id"] = speckle_instance.definitionId
    if hasattr(speckle_instance, "maxDepth"):
        instance_obj["max_depth"] = speckle_instance.maxDepth

    final_matrix = (
        mathutils.Matrix.Translation(location)
        @ rotation.to_matrix().to_4x4()
        @ mathutils.Matrix.Diagonal(scale_vector).to_4x4()
    )

    instance_obj.matrix_world = final_matrix

    return instance_obj
