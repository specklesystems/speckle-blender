"""
Functions for converting Blender mesh objects to Speckle mesh objects.
"""

from typing import Dict, List, cast

import bpy
from bpy.types import Mesh as BMesh
from bpy.types import MeshPolygon, Object
from mathutils import Matrix as MMatrix
from mathutils import Vector as MVector

from specklepy.objects.base import Base
from specklepy.objects.geometry.mesh import Mesh
from .utils import to_speckle_name


def mesh_to_speckle(
    blender_object: Object, 
    data: bpy.types.Mesh, 
    units_scale: float, 
    units: str
) -> Base:
    """
    Convert a Blender mesh object to a Speckle Base object with display value.
    
    Args:
        blender_object: The Blender object to convert
        data: The Blender mesh data
        units_scale: Scale factor to convert to desired units
        units: The desired units (e.g. 'm', 'ft')
        
    Returns:
        A Speckle Base object with the mesh as display value
    """
    # Create a base object to hold the mesh
    b = Base()
    b["name"] = to_speckle_name(blender_object)
    b["@displayValue"] = mesh_to_speckle_meshes(blender_object, data, units_scale, units)
    return b


def mesh_to_speckle_meshes(
    blender_object: Object, 
    data: bpy.types.Mesh, 
    units_scale: float, 
    units: str
) -> List[Mesh]:
    """
    Convert a Blender mesh to a list of Speckle meshes (one per material).
    
    Args:
        blender_object: The Blender object containing the mesh
        data: The Blender mesh data
        units_scale: Scale factor to convert to desired units
        units: The desired units (e.g. 'm', 'ft')
        
    Returns:
        A list of Speckle Mesh objects
    """
    # Validate input
    assert isinstance(data, BMesh), "Data must be a Blender mesh"
    assert units_scale > 0, "Units scale must be positive"
    
    # Categorize polygons by material index
    submesh_data: Dict[int, List[MeshPolygon]] = {}
    for p in data.polygons:
        if p.material_index not in submesh_data:
            submesh_data[p.material_index] = []
        submesh_data[p.material_index].append(p)

    # Transform vertices
    transform = cast(MMatrix, blender_object.matrix_world)
    scaled_vertices = [tuple(transform @ x.co * units_scale) for x in data.vertices]

    # Create Speckle meshes for each material
    submeshes = []
    index_counter = 0
    
    for material_index in submesh_data:
        index_mapping: Dict[int, int] = {}

        mesh_area = 0
        m_verts: List[float] = []
        m_faces: List[int] = []
        m_texcoords: List[float] = []
        
        for face in submesh_data[material_index]:
            # Get vertices indices for this face
            u_indices = face.vertices
            m_faces.append(len(u_indices))

            # Calculate face area
            mesh_area += face.area
            
            # Map vertices and UVs
            for u_index in u_indices:
                if u_index not in index_mapping:
                    # Create mapping between index in blender mesh and new index in speckle submesh
                    index_mapping[u_index] = len(m_verts) // 3
                    vert = scaled_vertices[u_index]
                    m_verts.append(vert[0])
                    m_verts.append(vert[1])
                    m_verts.append(vert[2])

                # Add UV coordinates if available
                if data.uv_layers.active:
                    vt = data.uv_layers.active.data[index_counter]
                    uv = cast(MVector, vt.uv)
                    m_texcoords.extend([uv.x, uv.y])

                m_faces.append(index_mapping[u_index])
                index_counter += 1

        # Create the Speckle mesh
        speckle_mesh = Mesh(
            vertices=m_verts,
            faces=m_faces,
            colors=[],
            textureCoordinates=m_texcoords,
            units=units,
        )
        
        # Calculate and set mesh properties
        if len(m_verts) > 0:
            speckle_mesh.area = mesh_area
            
            # Check if mesh is closed to calculate volume
            if is_closed_mesh(m_faces):
                volume = speckle_mesh.calculate_volume()
                speckle_mesh.volume = volume
        
        submeshes.append(speckle_mesh)

    return submeshes


def is_closed_mesh(faces: List[int]) -> bool:
    edge_counts = {}
    
    i = 0
    while i < len(faces):
        vertex_count = faces[i]
        for j in range(vertex_count):
            v1 = faces[i + 1 + j]
            v2 = faces[i + 1 + ((j + 1) % vertex_count)]
            edge = tuple(sorted([v1, v2]))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            
        i += vertex_count + 1
        
    return all(count == 2 for count in edge_counts.values())
