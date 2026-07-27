"""Bakes a parsed bundle straight into Blender data-blocks.

The direct-bake receive path, modelled on Rhino's ``IArtifactHostObjectBuilder``:
parquet arrays go to ``bpy.data`` without ever being reconstituted into a Speckle
``Base`` graph. Publishing already wrote world-baked geometry (Blender's
direct-display dialect), so a mesh's coordinates are final — the object is
created at the origin with the mesh carrying its own world position, exactly
inverting ``mesh_to_speckle_meshes``.

Collection instances are the one exception, as they are on the publish side: an
INSTANCE node becomes an empty with ``instance_type = 'COLLECTION'`` pointing at
the definition's collection, and the placement transform goes on the empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix
from specklepy.bundle import sgeo
from specklepy.objects.models.units import (
    get_scale_factor_to_meters,
    get_units_from_string,
)

from ..utils import create_material_from_proxy
from .bundle_reader import (
    BundleGeometry,
    BundleMaterial,
    BundleObject,
    ReceivedBundle,
)

# geometries.type labels we can turn into Blender data. Everything else is a
# genuine gap in the decoder, not a malformed bundle.
_DECODABLE_TYPES = frozenset({"mesh"})


@dataclass
class BakeResult:
    """What a bake produced, and what it could not."""

    objects: Dict[str, object] = field(default_factory=dict)
    root_collection: Optional[bpy.types.Collection] = None
    # geometry type -> how many blobs were skipped for want of a decoder. An
    # object whose geometry is *entirely* undecodable is dropped outright.
    skipped_by_type: Dict[str, int] = field(default_factory=dict)
    # (application_id, reason) for geometry that failed to decode
    decode_errors: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return sum(self.skipped_by_type.values())


def _scale_for(units: Optional[str]) -> float:
    """Scale factor from a bundle unit string into the Blender scene."""
    if not units:
        return 1.0
    unit_scale = get_scale_factor_to_meters(get_units_from_string(units))
    return unit_scale / bpy.context.scene.unit_settings.scale_length


class _MaterialShim:
    """Adapts a :class:`BundleMaterial` to what ``create_material_from_proxy``
    duck-types on.

    The bundle stores the diffuse colour in an ``argb`` column while the classic
    path reads ``RenderMaterial.diffuse``; the values are the same packed int, so
    a shim is enough to reuse the existing Principled node graph rather than
    growing a second copy of it.
    """

    def __init__(self, material: BundleMaterial) -> None:
        self.diffuse = material.argb
        self.opacity = material.opacity
        self.metalness = material.metalness
        self.roughness = material.roughness
        self.name = material.name


def _build_materials(bundle: ReceivedBundle) -> Dict[int, bpy.types.Material]:
    materials: Dict[int, bpy.types.Material] = {}
    for node_id, material in bundle.materials.items():
        name = material.name or f"Material_{node_id}"
        materials[node_id] = create_material_from_proxy(_MaterialShim(material), name)
    return materials


def _build_collections(
    bundle: ReceivedBundle, root_collection: bpy.types.Collection
) -> Dict[int, bpy.types.Collection]:
    """Recreate the CONTAINER tree under ``root_collection``.

    The published root maps onto the caller's root rather than nesting inside it,
    so a load does not add a redundant folder level.
    """
    created: Dict[int, bpy.types.Collection] = {}
    root_id = bundle.root_collection_id
    if root_id is not None:
        created[root_id] = root_collection

    def link_children(parent_id: Optional[int]) -> None:
        parent = created.get(parent_id) if parent_id is not None else root_collection
        for child in bundle.child_collections(parent_id):
            if child.node_id in created:
                continue
            collection = bpy.data.collections.new(child.name)
            (parent or root_collection).children.link(collection)
            created[child.node_id] = collection
            link_children(child.node_id)

    link_children(root_id)
    # Any CONTAINER not reachable from the root (a broken def_ref) still needs a
    # home, or its objects would silently vanish.
    for node_id, child in bundle.collections.items():
        if node_id not in created:
            collection = bpy.data.collections.new(child.name)
            root_collection.children.link(collection)
            created[node_id] = collection
    return created


def _decode_meshes(
    geometries: List[BundleGeometry],
) -> Tuple[List[sgeo.DecodedMesh], List[str]]:
    """Decode the mesh blobs of one object, collecting per-blob failures."""
    decoded: List[sgeo.DecodedMesh] = []
    errors: List[str] = []
    for geometry in geometries:
        try:
            decoded.append(sgeo.decode_mesh(geometry.content))
        except sgeo.SgeoDecodeError as e:
            errors.append(str(e))
    return decoded, errors


def _mesh_datablock(
    name: str,
    meshes: List[sgeo.DecodedMesh],
    materials: List[Optional[bpy.types.Material]],
) -> bpy.types.Mesh:
    """Merge one object's display meshes into a single Blender mesh.

    Mirrors ``meshes_to_native`` on the classic path — same vertex-offset join
    and same per-face-range material assignment — but reads the flat SGEO arrays
    directly instead of walking ``Mesh`` objects.
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
        scale = _scale_for(mesh.units)
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
            if vertex_count < 3 or i + vertex_count >= len(faces) + 1:
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


def _apply_properties(blender_object: bpy.types.Object, obj: BundleObject) -> None:
    """Write the object's eav properties back as Blender custom properties.

    Only the ``properties.`` subtree round-trips: ``name`` and ``speckle_type``
    were bare root scalars describing the object itself, not user data.
    """
    blender_object["applicationId"] = obj.application_id
    if obj.speckle_type:
        blender_object["speckle_type"] = obj.speckle_type
    for path, value in obj.properties.items():
        key = path[len("properties.") :] if path.startswith("properties.") else path
        if key and value is not None:
            blender_object[key] = value


def _placement_matrix(transform: List[float], units: Optional[str]) -> Matrix:
    """Turn a placement's 16 row-major doubles into a Blender matrix.

    The translation is unit-scaled but the rotation/shear block is not — scaling
    the whole matrix would scale the basis vectors too and shrink the instance.
    """
    if len(transform) != 16:
        return Matrix.Identity(4)
    matrix = Matrix([transform[0:4], transform[4:8], transform[8:12], transform[12:16]])
    scale = _scale_for(units)
    if scale != 1.0:
        for row in range(3):
            matrix[row][3] *= scale
    return matrix


# ── orchestration ───────────────────────────────────────────────────────────


def bake_bundle(
    bundle: ReceivedBundle,
    root_collection_name: str,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> BakeResult:
    """Bake a whole bundle into the current scene.

    Ordering is load-bearing: definitions must exist as collections before a
    placement can point an empty at one, and every object must exist before
    SUBELEMENT parenting can resolve both ends.
    """
    result = BakeResult()

    root_collection = bpy.data.collections.new(root_collection_name)
    bpy.context.scene.collection.children.link(root_collection)
    result.root_collection = root_collection

    materials = _build_materials(bundle)
    collections = _build_collections(bundle, root_collection)

    definition_collections = _build_definitions(bundle, materials, result)

    for obj in bundle.objects:
        target = collections.get(obj.collection_id, root_collection)

        if obj.is_placement:
            blender_object = _bake_placement(
                obj, bundle, definition_collections, instance_loading_mode
            )
        else:
            blender_object = _bake_object(obj, bundle, materials, result)

        if blender_object is None:
            continue

        _apply_properties(blender_object, obj)
        if blender_object.name not in target.objects:
            target.objects.link(blender_object)
        result.objects[obj.application_id] = blender_object

    _parent_subelements(bundle, result)
    return result


def _bake_object(
    obj: BundleObject,
    bundle: ReceivedBundle,
    materials: Dict[int, bpy.types.Material],
    result: BakeResult,
) -> Optional[bpy.types.Object]:
    """Bake one ordinary (non-placement) object."""
    geometries = [
        bundle.geometries[k] for k in obj.geometry_ks if k in bundle.geometries
    ]
    if not geometries:
        # properties-only, e.g. a metaball sibling — a real object with no shape
        return _empty_object(obj)

    decodable = _partition_decodable(geometries, result)
    if not decodable:
        # Every display geometry needs a decoder we do not have yet (today: the
        # SGEO curve family). Drop the object rather than leaving a shapeless
        # placeholder behind — the per-type tally is reported to the user, and a
        # reload once the decoder lands brings the real geometry in.
        return None

    meshes, errors = _decode_meshes(decodable)
    for error in errors:
        result.decode_errors.append((obj.application_id, error))
    if not meshes:
        # had geometry, produced none — same treatment as an undecodable type,
        # but the cause is a bad blob and is reported through decode_errors
        return None

    mesh_materials = [
        materials.get(bundle.geometry_materials.get(g.k, -1)) for g in decodable
    ]
    name = obj.name or obj.application_id
    data = _mesh_datablock(f"{name}.{obj.k}", meshes, mesh_materials)
    return bpy.data.objects.new(name, data)


def _partition_decodable(
    geometries: List[BundleGeometry], result: BakeResult
) -> List[BundleGeometry]:
    """Return the geometries we can decode, tallying the ones we cannot.

    The tally is per geometry blob rather than per object, so an object with one
    mesh and one curve reports the curve it lost even though the object itself
    still lands.
    """
    decodable: List[BundleGeometry] = []
    for geometry in geometries:
        if geometry.type in _DECODABLE_TYPES:
            decodable.append(geometry)
        else:
            result.skipped_by_type[geometry.type] = (
                result.skipped_by_type.get(geometry.type, 0) + 1
            )
    return decodable


def _empty_object(obj: BundleObject) -> bpy.types.Object:
    """A shapeless object that still carries its name and properties."""
    return bpy.data.objects.new(obj.name or obj.application_id, None)


def _build_definitions(
    bundle: ReceivedBundle,
    materials: Dict[int, bpy.types.Material],
    result: BakeResult,
) -> Dict[int, bpy.types.Collection]:
    """Turn each DEFINITION node into a collection of its member objects.

    Members are grouped by DEFINES ordinal — every geometry fragment of one
    member shares that member's ordinal, which is exactly what lets the
    fragments regroup into one object here. Definition collections are not
    linked into the scene; only placements reference them, which is what keeps
    an instanced "library" out of the visible scene tree.
    """
    definition_collections: Dict[int, bpy.types.Collection] = {}
    if not bundle.definitions:
        return definition_collections

    for node_id, definition in bundle.definitions.items():
        name = definition.name or f"Definition_{node_id}"
        collection = bpy.data.collections.new(name)
        definition_collections[node_id] = collection

        for ordinal in sorted(definition.members):
            geometries = [
                bundle.geometries[k]
                for k in definition.members[ordinal]
                if k in bundle.geometries
            ]
            decodable = _partition_decodable(geometries, result)
            if not decodable:
                continue

            meshes, errors = _decode_meshes(decodable)
            for error in errors:
                result.decode_errors.append((f"{name}[{ordinal}]", error))
            if not meshes:
                continue

            member_materials = [
                materials.get(bundle.geometry_materials.get(g.k, -1)) for g in decodable
            ]
            member_name = f"{name}.{ordinal}"
            data = _mesh_datablock(member_name, meshes, member_materials)
            collection.objects.link(bpy.data.objects.new(member_name, data))

    # nested placements: a definition member that is itself an instance
    for node_id, definition in bundle.definitions.items():
        for ordinal, instance_id in definition.nested.items():
            instance = bundle.instances.get(instance_id)
            if instance is None or instance.def_ref is None:
                continue
            nested = definition_collections.get(instance.def_ref)
            if nested is None:
                continue
            empty = bpy.data.objects.new(f"{nested.name}.{ordinal}", None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = nested
            empty.matrix_world = _placement_matrix(instance.transform, instance.units)
            definition_collections[node_id].objects.link(empty)

    return definition_collections


def _bake_placement(
    obj: BundleObject,
    bundle: ReceivedBundle,
    definition_collections: Dict[int, bpy.types.Collection],
    instance_loading_mode: str,
) -> Optional[bpy.types.Object]:
    """A collection instance: an empty pointing at the definition's collection.

    The publish side removed the collection's ``instance_offset`` from the
    placement transform and baked each member's ``matrix_world`` as
    definition-local geometry, so the transform applies here with no pivot
    correction — Blender's own offset is zero on a collection we created.
    """
    instance = bundle.instances.get(obj.instance_id or -1)
    if instance is None or instance.def_ref is None:
        return None
    definition = definition_collections.get(instance.def_ref)
    if definition is None:
        return None

    name = obj.name or obj.application_id
    if instance_loading_mode == "LINKED_DUPLICATES":
        # bake a real copy per member instead of one instancing empty
        parent = bpy.data.objects.new(name, None)
        parent.matrix_world = _placement_matrix(instance.transform, instance.units)
        for member in definition.objects:
            copy = member.copy()
            copy.parent = parent
            bpy.context.scene.collection.objects.link(copy)
        return parent

    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = definition
    empty.matrix_world = _placement_matrix(instance.transform, instance.units)
    return empty


def _parent_subelements(bundle: ReceivedBundle, result: BakeResult) -> None:
    """Re-establish SUBELEMENT parenting once every object exists.

    Only metaball families use this today: the basis owns the merged blob and
    its siblings hang off it carrying properties only. Parenting is set with
    ``matrix_parent_inverse`` left at identity because the children have no
    geometry to displace.
    """
    for obj in bundle.objects:
        if not obj.subelement_ids:
            continue
        parent = result.objects.get(obj.application_id)
        if parent is None:
            continue
        for child_id in obj.subelement_ids:
            child = result.objects.get(child_id)
            if child is not None and child is not parent:
                child.parent = parent
