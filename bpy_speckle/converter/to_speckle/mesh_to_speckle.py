from typing import Dict, List, cast

import bpy
from bpy.types import Mesh as BMesh
from bpy.types import MeshPolygon, Object
from mathutils import Matrix as MMatrix
from mathutils import Vector as MVector

from specklepy.objects.base import Base
from specklepy.objects.geometry.mesh import Mesh


def mesh_to_speckle(
    blender_object: Object, data: bpy.types.Mesh, units_scale: float, units: str
) -> Base:
    """
    convert a Blender mesh object
    """
    meshes = mesh_to_speckle_meshes(blender_object, data, units_scale, units)

    for mesh in meshes:
        mesh.applicationId = blender_object.name

    return meshes


def mesh_to_speckle_meshes(
    blender_object: Object, data: bpy.types.Mesh, units_scale: float, units: str
) -> List[Mesh]:
    """
    convert a Blender mesh to a list of Speckle meshes
    each face corner (loop) gets its own vertex
    """
    assert isinstance(data, BMesh), "Data must be a Blender mesh"
    assert units_scale > 0, "Units scale must be positive"

    submesh_data: Dict[int, List[MeshPolygon]] = {}
    for p in data.polygons:
        if p.material_index not in submesh_data:
            submesh_data[p.material_index] = []
        submesh_data[p.material_index].append(p)

    transform = cast(MMatrix, blender_object.matrix_world)
    normal_transform = transform.to_3x3().inverted().transposed()

    submeshes = []

    for material_index in submesh_data:
        mesh_area = 0
        m_verts: List[float] = []
        m_faces: List[int] = []
        m_texcoords: List[float] = []
        m_normals: List[float] = []

        vertex_counter = 0

        for face in submesh_data[material_index]:
            mesh_area += face.area

            loop_indices = face.loop_indices
            m_faces.append(len(loop_indices))

            for loop_index in loop_indices:
                loop = data.loops[loop_index]

                vertex = data.vertices[loop.vertex_index]
                transformed_vertex = transform @ vertex.co * units_scale

                m_verts.extend(
                    [transformed_vertex.x, transformed_vertex.y, transformed_vertex.z]
                )

                # get and transform the loop normal
                # try to get split normal, fallback to face normal if not available
                try:
                    if hasattr(loop, "normal") and len(loop.normal) > 0:
                        # Use split normal from loop
                        loop_normal = normal_transform @ loop.normal
                    else:
                        # Fallback to face normal
                        loop_normal = normal_transform @ face.normal
                except:  # noqa: E722
                    # Final fallback: use face normal
                    loop_normal = normal_transform @ face.normal

                loop_normal.normalize()
                m_normals.extend([loop_normal.x, loop_normal.y, loop_normal.z])

                # add UV coordinates if available
                if data.uv_layers.active:
                    uv_data = data.uv_layers.active.data[loop_index]
                    uv = cast(MVector, uv_data.uv)
                    m_texcoords.extend([uv.x, uv.y])

                m_faces.append(vertex_counter)
                vertex_counter += 1

        speckle_mesh = Mesh(
            vertices=m_verts,
            faces=m_faces,
            colors=[],
            textureCoordinates=m_texcoords,
            vertexNormals=m_normals,
            units=units,
        )

        if len(m_verts) > 0:
            speckle_mesh.area = mesh_area

            if is_closed_mesh(m_faces):
                volume = speckle_mesh.calculate_volume()
                speckle_mesh.volume = volume

        submeshes.append(speckle_mesh)

    return submeshes


def is_closed_mesh(faces: List[int]) -> bool:
    """
    check if a mesh is closed by verifying that each edge is shared by exactly 2 faces.
    """
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
