"""Decode and construct mesh-family SGEO primitives."""

from typing import Dict, List, Optional, Tuple

import bpy
from specklepy.bundle import sgeo
from specklepy.bundle.bundle_reader import Geometry

from ..transforms import scale_for


def build_mesh_object(
    name: str,
    data_name: str,
    geometries: List[Geometry],
    materials: List[Optional[bpy.types.Material]],
) -> Tuple[Optional[bpy.types.Object], List[str]]:
    """Decode and merge one object's mesh geometry into one Blender object."""
    meshes, errors = _decode_meshes(geometries)
    if not meshes:
        return None, errors
    data = _mesh_datablock(data_name, meshes, materials)
    return bpy.data.objects.new(name, data), errors


def _decode_meshes(
    geometries: List[Geometry],
) -> Tuple[List[sgeo.DecodedMesh], List[str]]:
    """Decode the mesh-family blobs of one object, collecting per-blob failures.

    ``mesh`` takes the raw-array fast path; ``box`` is an analytical primitive
    that becomes the same flat arrays, so both merge into one data-block.
    """
    decoded: List[sgeo.DecodedMesh] = []
    errors: List[str] = []
    for geometry in geometries:
        try:
            if geometry.type == "box":
                decoded.append(_box_to_mesh(sgeo.decode(geometry.content)))
            else:
                decoded.append(sgeo.decode_mesh(geometry.content))
        except sgeo.SgeoDecodeError as e:
            errors.append(str(e))
    return decoded, errors


def _box_to_mesh(box) -> sgeo.DecodedMesh:
    """Flatten a Box into the eight corners and six quads it describes."""
    plane = box.basePlane
    o, x, y, z = plane.origin, plane.xdir, plane.ydir, plane.normal
    corners: List[float] = []
    for zs in (box.zSize.start, box.zSize.end):
        for ys in (box.ySize.start, box.ySize.end):
            for xs in (box.xSize.start, box.xSize.end):
                corners.extend(
                    (
                        o.x + x.x * xs + y.x * ys + z.x * zs,
                        o.y + x.y * xs + y.y * ys + z.y * zs,
                        o.z + x.z * xs + y.z * ys + z.z * zs,
                    )
                )
    # corner order above is (z, y, x) least-significant-x, so 0-3 is the bottom
    # face and 4-7 the top, each wound x-then-y
    faces = [
        4, 0, 1, 3, 2,  # bottom
        4, 4, 6, 7, 5,  # top
        4, 0, 4, 5, 1,  # -y
        4, 2, 3, 7, 6,  # +y
        4, 0, 2, 6, 4,  # -x
        4, 1, 5, 7, 3,  # +x
    ]  # fmt: skip
    return sgeo.DecodedMesh(
        vertices=corners,
        faces=faces,
        vertex_normals=[],
        texture_coordinates=[],
        colors=[],
        units=box.units,
    )


def _mesh_datablock(
    name: str,
    meshes: List[sgeo.DecodedMesh],
    materials: List[Optional[bpy.types.Material]],
) -> bpy.types.Mesh:
    """Merge one object's display meshes into a single Blender mesh.

    A vertex-offset join with per-face-range material assignment, reading the
    flat SGEO arrays directly instead of walking ``Mesh`` objects.
    """
    blender_mesh = bpy.data.meshes.new(name)

    all_vertices: List[Tuple[float, float, float]] = []
    all_faces: List[List[int]] = []
    all_normals: List[Tuple[float, float, float]] = []
    # (start_face, end_face, mesh_index) so materials can be assigned per source mesh
    face_ranges: List[Tuple[int, int, int]] = []
    has_normals = any(m.vertex_normals for m in meshes)

    vertex_offset = 0
    current_face = 0

    for mesh_index, mesh in enumerate(meshes):
        scale = scale_for(mesh.units)
        vertices = mesh.vertices
        for i in range(0, len(vertices), 3):
            all_vertices.append(
                (
                    vertices[i] * scale,
                    vertices[i + 1] * scale,
                    vertices[i + 2] * scale,
                )
            )

        start_face = current_face
        normals = mesh.vertex_normals
        faces = mesh.faces
        i = 0
        while i < len(faces):
            vertex_count = faces[i]
            # a corrupt count would run off the end; stop rather than raise so the
            # rest of the object still lands
            # the loop reads up to faces[i + vertex_count], so that index must exist
            if vertex_count < 3 or i + vertex_count >= len(faces):
                break
            face = []
            for j in range(1, vertex_count + 1):
                index = faces[i + j]
                face.append(index + vertex_offset)
                if has_normals:
                    n = index * 3
                    if normals and n + 2 < len(normals):
                        all_normals.append((normals[n], normals[n + 1], normals[n + 2]))
                    else:
                        # zero vector reads as "auto normal" to Blender
                        all_normals.append((0.0, 0.0, 0.0))
            all_faces.append(face)
            i += vertex_count + 1
            current_face += 1

        vertex_offset += len(vertices) // 3
        if current_face > start_face:
            face_ranges.append((start_face, current_face - 1, mesh_index))

    blender_mesh.from_pydata(all_vertices, [], all_faces)
    blender_mesh.update()

    if has_normals and len(all_normals) == len(blender_mesh.loops):
        blender_mesh.normals_split_custom_set(all_normals)
    else:
        blender_mesh.shade_smooth()

    _assign_materials(blender_mesh, materials, face_ranges)
    return blender_mesh


def _assign_materials(
    blender_mesh: bpy.types.Mesh,
    materials: List[Optional[bpy.types.Material]],
    face_ranges: List[Tuple[int, int, int]],
) -> None:
    """Bind each source mesh's material to the faces that came from it.

    HAS_MATERIAL binds to geometry, not to the object, so one object's two
    display meshes can legitimately carry different materials — hence slots
    rather than a single object-level material.
    """
    slot_of: Dict[str, int] = {}
    for start, end, mesh_index in face_ranges:
        material = materials[mesh_index] if mesh_index < len(materials) else None
        if material is None:
            continue
        if material.name not in slot_of:
            blender_mesh.materials.append(material)
            slot_of[material.name] = len(blender_mesh.materials) - 1
        slot = slot_of[material.name]
        for face_index in range(start, end + 1):
            if face_index < len(blender_mesh.polygons):
                blender_mesh.polygons[face_index].material_index = slot
