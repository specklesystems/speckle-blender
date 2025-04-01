from typing import Any, Iterable, List, Optional, Tuple, Dict
from specklepy.objects import Base
from specklepy.objects.geometry import Line, Polyline, Mesh
from specklepy.objects.models.units import (
    get_units_from_string,
    get_scale_factor_to_meters,
)
import bpy
from bpy.types import Object
from ..converter.utils import create_material_from_proxy

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

        # Adjust for Blender's unit scale setting
        blender_unit_scale = bpy.context.scene.unit_settings.scale_length

        # Calculate final scale factor
        scale = unit_scale / blender_unit_scale

    return scale


def generate_unique_name(speckle_object: Base) -> Tuple[str, str]:
    """
    generates unique name for converted blender objects and data-blocks
    """
    # Check if speckle object is a data object
    # Since every data object has name, use it in naming
    # If not extract base name from speckle type itself
    if (
        "DataObject" in speckle_object.speckle_type
        and hasattr(speckle_object, "name")
        and speckle_object.name
    ):
        base_name = speckle_object.name
    else:
        parts = speckle_object.speckle_type.split(".")
        base_name = parts[-1]

    # Get the speckle id
    speckle_id = ""
    if hasattr(speckle_object, "id") and speckle_object.id:
        speckle_id = speckle_object.id
    else:
        raise KeyError("No id has been found!")  # is that even possible?

    # Define object name - should be simple
    object_name = base_name

    # Define data-block name - should include ID
    datablock_name = f"{base_name}.{speckle_id}"

    return object_name, datablock_name


def convert_to_native(
    speckle_object: Base,
    material_mapping: Optional[Dict[str, bpy.types.Material]] = None,
) -> Optional[Object]:
    """
    converts a speckle object to blender object with material support
    """
    # Determine scale factor based on object units
    scale = get_scale_factor(speckle_object)

    # Generate names
    object_name, data_block_name = generate_unique_name(speckle_object)

    converted_object = None

    # Initialize material mapping if not provided
    if material_mapping is None:
        material_mapping = {}

    # Try direct conversion based on object type
    if isinstance(speckle_object, Line):
        converted_object = line_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Polyline):
        converted_object = polyline_to_native(
            speckle_object, object_name, data_block_name, scale
        )
    elif isinstance(speckle_object, Mesh):
        converted_object = mesh_to_native(
            speckle_object, object_name, data_block_name, scale, material_mapping
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

            # If there are multiple objects, parent remaining ones to the first
            for child in children[1:]:
                child.parent = converted_object

    if converted_object:
        # Store Speckle ID in custom property
        converted_object["speckle_id"] = speckle_object.id

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

    # Get mesh and children
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
        # Only apply if the child doesn't already have a material
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
        # Use data_block_name (the name with ID) for the mesh datablock
        mesh = meshes_to_native(
            speckle_object, meshes, data_block_name, scale, material_mapping
        )

    for item in others:
        try:
            blender_object = convert_to_native(item, material_mapping)
            if blender_object:
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
    # Check if the line has valid start and end points
    if not speckle_line.start or not speckle_line.end:
        raise ValueError("Line is missing start or end point")

    # Create curve data with data_block_name (the name with ID)
    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    # Create a new spline in the curve
    spline = curve.splines.new("POLY")
    spline.points.add(1)

    # Set the coordinates with scale applied
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

    # Create object with object_name (the simple name)
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
    # Check if polyline has valid points
    if not speckle_polyline.value or len(speckle_polyline.value) < 6:
        raise ValueError("Polyline must have at least two points")

    # Create curve data with data_block_name (the name with ID)
    curve = bpy.data.curves.new(data_block_name, type="CURVE")
    curve.dimensions = "3D"

    # Create a new spline in the curve
    spline = curve.splines.new("POLY")

    # Get the number of points in the polyline
    num_points = len(speckle_polyline.value) // 3  # divide by 3 to get point count

    # Add the required number of points to the spline
    if num_points > 1:
        spline.points.add(num_points - 1)

    # Set the coordinates for each point with scale applied
    for i in range(num_points):
        # Note: Blender curve points are 4D (x, y, z, w) where w is weight
        spline.points[i].co = (
            float(speckle_polyline.value[i * 3]) * scale,
            float(speckle_polyline.value[i * 3 + 1]) * scale,
            float(speckle_polyline.value[i * 3 + 2]) * scale,
            1.0,
        )

    # Set cyclic property if the polyline is closed
    if hasattr(speckle_polyline, "closed") and speckle_polyline.closed:
        spline.use_cyclic_u = True

    # Create object with object_name (the simple name)
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
    # Create mesh data with data_block_name (the name with ID)
    mesh = mesh_to_native_mesh(speckle_mesh, data_block_name, scale)

    # Create object with object_name (the simple name)
    mesh_obj = bpy.data.objects.new(object_name, mesh)

    # Add vertex colors if present
    if len(speckle_mesh.colors) > 0:
        add_vertex_colors(mesh, speckle_mesh.colors)

    # Add texture coordinates if present
    if len(speckle_mesh.textureCoordinates) > 0:
        add_texture_coordinates(mesh, speckle_mesh.textureCoordinates)

    # Apply material if available for this mesh
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
    # Check if the mesh has valid vertices and faces
    if not speckle_mesh.vertices or not speckle_mesh.faces:
        raise ValueError("Mesh has no vertices or faces")

    # Create a new mesh object with the provided name (with ID)
    blender_mesh = bpy.data.meshes.new(name)

    # Prepare vertices and faces with scale applied
    vertices = []
    for i in range(0, len(speckle_mesh.vertices), 3):
        vertices.append(
            (
                float(speckle_mesh.vertices[i]) * scale,
                float(speckle_mesh.vertices[i + 1]) * scale,
                float(speckle_mesh.vertices[i + 2]) * scale,
            )
        )

    # Extract faces from the Speckle mesh format
    faces = []
    i = 0
    while i < len(speckle_mesh.faces):
        vertex_count = speckle_mesh.faces[i]
        face = []
        for j in range(1, vertex_count + 1):
            vertex_index = speckle_mesh.faces[i + j]
            face.append(vertex_index)
        faces.append(face)
        i += vertex_count + 1

    # Create the mesh from vertices and faces
    blender_mesh.from_pydata(vertices, [], faces)
    blender_mesh.update()

    return blender_mesh


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
    # If there's only one mesh, use the simpler conversion function
    if len(meshes) == 1:
        blender_mesh = mesh_to_native_mesh(meshes[0], name, scale)

        # Apply material if available for this mesh
        if material_mapping and hasattr(meshes[0], "applicationId"):
            app_id = meshes[0].applicationId
            if app_id in material_mapping:
                material = material_mapping[app_id]
                blender_mesh.materials.append(material)

        return blender_mesh

    # Create a new mesh object with the provided name
    blender_mesh = bpy.data.meshes.new(name)

    # Track face ranges for each mesh for material assignment
    mesh_face_ranges = []  # List of (start_face, end_face, mesh_index)
    current_face = 0

    # Track materials needed
    mesh_materials = {}  # Maps mesh index to material

    # Process all meshes and combine them
    all_vertices = []
    all_faces = []
    vertex_offset = 0

    # First pass: collect vertices, faces, and track face ranges
    for mesh_idx, mesh in enumerate(meshes):
        start_face = current_face

        # Check if this mesh has a material
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
            face = []
            for j in range(1, vertex_count + 1):
                vertex_index = mesh.faces[i + j]
                face.append(vertex_index + vertex_offset)
            all_faces.append(face)
            i += vertex_count + 1
            face_count += 1
            current_face += 1

        # Update vertex offset for the next mesh
        vertex_offset += len(mesh.vertices) // 3

        # Store face range if this mesh has faces
        if face_count > 0:
            mesh_face_ranges.append((start_face, current_face - 1, mesh_idx))

    # Create the combined mesh
    blender_mesh.from_pydata(all_vertices, [], all_faces)
    blender_mesh.update()

    # If we have materials, add them to the mesh
    if mesh_materials:
        # First add all materials to the mesh
        materials_added = set()
        material_indices = {}  # Maps material name to index in the mesh

        for mesh_idx, material in mesh_materials.items():
            if material.name not in materials_added:
                blender_mesh.materials.append(material)
                material_indices[material.name] = len(blender_mesh.materials) - 1
                materials_added.add(material.name)

        # Now assign materials to faces based on which mesh they came from
        for start_face, end_face, mesh_idx in mesh_face_ranges:
            if mesh_idx in mesh_materials:
                material = mesh_materials[mesh_idx]
                material_index = material_indices[material.name]

                # Assign this material to all faces in this range
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

    # Create a new UV layer
    if not blender_mesh.uv_layers:
        blender_mesh.uv_layers.new()

    uv_layer = blender_mesh.uv_layers.active

    # Set UV coordinates for each loop
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
    converts RenderMaterialProxies to Blender materials
    """
    assigned_objects = {}

    # check if object has renderMaterialProxies
    if not hasattr(speckle_object, "renderMaterialProxies"):
        print("No render material proxies found!")
        return assigned_objects

    # process each render material proxy
    for proxy in speckle_object.renderMaterialProxies:
        if not hasattr(proxy, "value") or not hasattr(proxy, "objects"):
            print("Render material proxy has no value or no object has assigned!")
            continue
        render_material = proxy.value
        material_name = getattr(render_material, "name")

        # create blender material
        blender_material = create_material_from_proxy(render_material, material_name)

        # map application ids to this material
        for applicationId in proxy.objects:
            assigned_objects[applicationId] = blender_material

    # return the mapping
    return assigned_objects
