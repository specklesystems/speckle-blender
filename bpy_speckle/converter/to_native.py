import bpy
import bmesh
from bpy.types import Object
from mathutils import Vector
from typing import Any, List, Optional, Tuple, Iterable
from specklepy.objects.base import Base
from specklepy.objects.geometry.line import Line
from specklepy.objects.geometry.mesh import Mesh
from specklepy.objects.geometry.polyline import Polyline

# Constants for naming and conversion
OBJECT_NAME_MAX_LENGTH = 62
OBJECT_NAME_SPECKLE_SEPARATOR = "::"
OBJECT_NAME_NUMERAL_SEPARATOR = "."

# Property aliases for finding geometry in various Speckle object types
DISPLAY_VALUE_PROPERTY_ALIASES = ["displayValue", "displayMesh", "displayStyle"]
ELEMENTS_PROPERTY_ALIASES = ["elements", "Elements", "@elements"]

def _has_native_conversion(speckle_object: Base) -> bool:
    """Check if object has a direct conversion method."""
    return isinstance(speckle_object, (Line, Mesh, Polyline))

def _has_fallback_conversion(speckle_object: Base) -> bool:
    """Check if object has displayValue properties that can be converted."""
    return any(getattr(speckle_object, alias, None) for alias in DISPLAY_VALUE_PROPERTY_ALIASES)

def can_convert_to_native(speckle_object: Base) -> bool:
    """Check if a Speckle object can be converted to Blender.
    
    Args:
        speckle_object: The Speckle object to check
        
    Returns:
        True if the object can be converted, False otherwise
    """
    return _has_native_conversion(speckle_object) or _has_fallback_conversion(speckle_object)

def convert_to_native(speckle_object: Base) -> Object:
    """Convert a Speckle object to a Blender object.
    
    Args:
        speckle_object: The Speckle object to convert
        
    Returns:
        A Blender object
    """
    # Generate a name for the object
    object_name = _generate_object_name(speckle_object)
    
    converted = None
    children = []
    
    # First try native conversion if available
    if isinstance(speckle_object, Line):
        converted = line_to_native(speckle_object, object_name)
    elif isinstance(speckle_object, Mesh):
        converted = mesh_to_native(speckle_object, object_name, 1.0)  # Using 1.0 as default scale
    elif isinstance(speckle_object, Polyline):
        converted = polyline_to_native(speckle_object, object_name)
    
    # If no native conversion was possible, try displayValue conversion
    if not converted:
        (converted, children) = display_value_to_native(
            speckle_object, object_name, 1.0  # Using 1.0 as default scale
        )
        if not converted and not children:
            raise ValueError(f"Failed to convert object: {speckle_object.speckle_type}")
    
    # Create a Blender object if the converter returned data instead of an object
    if not isinstance(converted, Object):
        blender_object = create_new_object(converted, object_name)
    else:
        blender_object = converted
    
    # Store Speckle ID
    if hasattr(blender_object, "speckle"):
        blender_object.speckle.object_id = str(speckle_object.id)
        blender_object.speckle.enabled = True
    
    # Parent children to the main object if any were created
    for child in children:
        child.parent = blender_object
    
    return blender_object

def line_to_native(speckle_line: Line, name: str) -> bpy.types.Curve:
    """Convert a Speckle line to a Blender curve.
    
    Args:
        speckle_line: The Speckle line to convert
        name: The name for the new Blender curve
        
    Returns:
        A Blender curve data block
    """
    # Check if the line has valid start and end points
    if not speckle_line.start or not speckle_line.end:
        raise ValueError("Line is missing start or end point")
    
    # Create a new curve data block
    blender_curve = bpy.data.curves.new(name, type="CURVE")
    blender_curve.dimensions = "3D"
    
    # Create a new spline in the curve
    spline = blender_curve.splines.new("POLY")
    spline.points.add(1)  # Add one point (default has 1, so total will be 2)
    
    # Set the coordinates
    # Note: Blender curve points are 4D (x, y, z, w) where w is weight
    spline.points[0].co = (
        float(speckle_line.start.x),
        float(speckle_line.start.y),
        float(speckle_line.start.z),
        1.0,
    )
    
    spline.points[1].co = (
        float(speckle_line.end.x),
        float(speckle_line.end.y),
        float(speckle_line.end.z),
        1.0,
    )
    
    return blender_curve

def mesh_to_native(speckle_mesh: Mesh, name: str, scale: float) -> bpy.types.Mesh:
    """Convert a Speckle mesh to a Blender mesh.
    
    Args:
        speckle_mesh: The Speckle mesh to convert
        name: The name for the new Blender mesh
        scale: The scale factor to apply
        
    Returns:
        A Blender mesh data block
    """
    # Check if mesh already exists with this name
    if name in bpy.data.meshes.keys():
        return bpy.data.meshes[name]
    
    # Create a new mesh data block
    blender_mesh = bpy.data.meshes.new(name=name)
    
    # Create a BMesh for easier manipulation
    bm = bmesh.new()
    
    # Add vertices
    add_vertices(speckle_mesh, bm, scale)
    bm.verts.ensure_lookup_table()
    
    # Add faces
    add_faces(speckle_mesh, bm, 0, 0)
    bm.faces.ensure_lookup_table()
    
    # Finalize and cleanup
    bm.to_mesh(blender_mesh)
    bm.free()
    
    return blender_mesh

def add_vertices(mesh: Mesh, bm: bmesh.types.BMesh, scale: float) -> None:
    """Add vertices from a Speckle mesh to a Blender BMesh.
    
    Args:
        mesh: The Speckle mesh containing vertices
        bm: The Blender BMesh to add vertices to
        scale: The scale factor to apply
    """
    if not mesh.vertices:
        return
    
    # Add vertices
    for i in range(0, len(mesh.vertices), 3):
        x = float(mesh.vertices[i]) * scale
        y = float(mesh.vertices[i + 1]) * scale
        z = float(mesh.vertices[i + 2]) * scale
        bm.verts.new(Vector((x, y, z)))

def add_faces(mesh: Mesh, bm: bmesh.types.BMesh, vertex_offset: int, material_index: int) -> None:
    """Add faces from a Speckle mesh to a Blender BMesh.
    
    Args:
        mesh: The Speckle mesh containing faces
        bm: The Blender BMesh to add faces to
        vertex_offset: Offset to apply to vertex indices
        material_index: Material index to assign to faces
    """
    if not mesh.faces:
        return
    
    # Ensure lookup table is up to date
    bm.verts.ensure_lookup_table()
    
    i = 0
    while i < len(mesh.faces):
        face_size = mesh.faces[i]
        i += 1
        
        # Skip invalid faces
        if face_size < 3:
            continue
        
        # Get vertices for this face
        verts = []
        for j in range(face_size):
            if i >= len(mesh.faces):
                break
                
            vert_idx = mesh.faces[i] + vertex_offset
            i += 1
            
            if vert_idx >= len(bm.verts):
                continue
                
            verts.append(bm.verts[vert_idx])
        
        # Create the face if we have enough valid vertices
        if len(verts) >= 3:
            try:
                face = bm.faces.new(verts)
                face.material_index = material_index
            except Exception as e:
                print(f"Failed to create face: {e}")

def polyline_to_native(speckle_polyline: Polyline, name: str) -> bpy.types.Curve:
    """Convert a Speckle polyline to a Blender curve.
    
    Args:
        speckle_polyline: The Speckle polyline to convert
        name: The name for the new Blender curve
        
    Returns:
        A Blender curve data block
    """
    # Get points from the polyline
    points = speckle_polyline.get_points()
    if not points:
        raise ValueError("Polyline has no points")
    
    # Create a new curve data block
    blender_curve = bpy.data.curves.new(name, type="CURVE")
    blender_curve.dimensions = "3D"
    
    # Create a new spline in the curve
    spline = blender_curve.splines.new("POLY")
    spline.points.add(len(points) - 1)  # Add points (default has 1, so add n-1 more)
    
    # Set the coordinates for each point
    # Note: Blender curve points are 4D (x, y, z, w) where w is weight
    for i, point in enumerate(points):
        spline.points[i].co = (
            float(point.x),
            float(point.y),
            float(point.z),
            1.0,
        )
    
    # If the polyline is closed, set the spline to be cyclic
    if speckle_polyline.is_closed():
        spline.use_cyclic_u = True
    
    return blender_curve

def display_value_to_native(
    speckle_object: Base, name: str, scale: float
) -> Tuple[Optional[bpy.types.Mesh], List[Object]]:
    """Convert displayValue properties to Blender objects.
    
    Args:
        speckle_object: The Speckle object to convert
        name: The name for the new Blender objects
        scale: The scale factor to apply
        
    Returns:
        Tuple of (converted mesh, list of child objects)
    """
    return _members_to_native(
        speckle_object, name, scale, DISPLAY_VALUE_PROPERTY_ALIASES, True
    )

def _members_to_native(
    speckle_object: Base,
    name: str,
    scale: float,
    members: Iterable[str],
    combineMeshes: bool,
) -> Tuple[Optional[bpy.types.Mesh], List[Object]]:
    """Convert specific members of a Speckle object to Blender objects.
    
    Args:
        speckle_object: The Speckle object to convert
        name: The name for the new Blender objects
        scale: The scale factor to apply
        members: The member properties to look for
        combineMeshes: Whether to combine meshes into one
        
    Returns:
        Tuple of (combined mesh, list of child objects)
    """
    meshes: List[Mesh] = []
    others: List[Base] = []
    
    for alias in members:
        display = getattr(speckle_object, alias, None)
        
        count = 0
        MAX_DEPTH = 255  # Prevent infinite recursion
        
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
            print(f"Traversal halted after exceeding depth {MAX_DEPTH}")
    
    # Convert meshes and other objects
    children: List[Object] = []
    mesh = None
    
    if meshes:
        mesh = meshes_to_native(speckle_object, meshes, name, scale)
    
    for item in others:
        try:
            blender_object = convert_to_native(item)
            children.append(blender_object)
        except Exception as ex:
            print(f"Failed to convert display value {item}: {ex}")
    
    return (mesh, children)

def meshes_to_native(element: Base, meshes: List[Mesh], name: str, scale: float) -> bpy.types.Mesh:
    """Convert multiple Speckle meshes to a single Blender mesh.
    
    Args:
        element: The parent Speckle object
        meshes: The Speckle meshes to convert
        name: The name for the new Blender mesh
        scale: The scale factor to apply
        
    Returns:
        A Blender mesh
    """
    if name in bpy.data.meshes.keys():
        return bpy.data.meshes[name]
    
    blender_mesh = bpy.data.meshes.new(name=name)
    
    bm = bmesh.new()
    
    # First pass: add vertices
    for mesh in meshes:
        add_vertices(mesh, bm, scale)
    
    bm.verts.ensure_lookup_table()
    
    # Second pass: add faces
    offset = 0
    for i, mesh in enumerate(meshes):
        if not mesh.vertices:
            continue
        
        add_faces(mesh, bm, offset, i)
        
        offset += len(mesh.vertices) // 3
    
    # Finalize and cleanup
    bm.to_mesh(blender_mesh)
    bm.free()
    
    return blender_mesh

def create_new_object(obj_data, desired_name: str) -> bpy.types.Object:
    """Create a new Blender object with a unique name.
    
    Args:
        obj_data: The data to use for the object (e.g., mesh, curve)
        desired_name: The desired name for the object
        
    Returns:
        A new Blender object
    """
    # Make sure the name is unique
    name = _make_unique_name(desired_name, bpy.data.objects.keys())
    
    # Create the object
    blender_object = bpy.data.objects.new(name, obj_data)
    
    # Link it to the active collection if possible
    if bpy.context.collection:
        bpy.context.collection.objects.link(blender_object)
    else:
        # If no active collection, link to scene collection
        bpy.context.scene.collection.objects.link(blender_object)
    
    return blender_object

def _make_unique_name(desired_name: str, existing_names) -> str:
    """Create a unique name by appending a number if necessary.
    
    Args:
        desired_name: The desired name
        existing_names: Collection of existing names to avoid duplicates
        
    Returns:
        A unique name
    """
    if desired_name not in existing_names:
        return desired_name
    
    # If name exists, append numbers until we find a unique one
    counter = 1
    while True:
        new_name = f"{desired_name}.{counter:03d}"
        if new_name not in existing_names:
            return new_name
        counter += 1

def _generate_object_name(speckle_object: Base) -> str:
    """Generate a name for a Blender object based on a Speckle object.
    
    Args:
        speckle_object: The Speckle object
        
    Returns:
        A name for the object
    """
    # Try to get a meaningful name
    name = getattr(speckle_object, "name", None)
    
    if not name:
        # Use the object type as a fallback
        speckle_type = speckle_object.speckle_type
        name = speckle_type.split(".")[-1]  # Get the last part of the type name
    
    # Truncate if necessary
    if len(name) > OBJECT_NAME_MAX_LENGTH - 10:  # Leave room for speckle ID
        name = name[:OBJECT_NAME_MAX_LENGTH - 10]
    
    # Add the Speckle ID for uniqueness
    if hasattr(speckle_object, "id") and speckle_object.id:
        return f"{name}{OBJECT_NAME_SPECKLE_SEPARATOR}{speckle_object.id[:8]}"
    else:
        return name