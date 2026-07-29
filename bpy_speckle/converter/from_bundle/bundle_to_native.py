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

# geometries.type labels grouped by the Blender data-block they become. A
# Blender object holds exactly one data-block, so an object whose display
# geometry spans families gets the dominant one and children for the rest.
#
# Blender itself only publishes mesh / curve / polyline / points, but a bundle
# from Rhino or Revit can carry the whole family, so all of it is handled.
_MESH_TYPES = frozenset({"mesh", "box"})
_CURVE_TYPES = frozenset(
    {"line", "polyline", "polycurve", "curve", "arc", "circle", "ellipse", "spiral"}
)
_POINT_TYPES = frozenset({"points"})
_DECODABLE_TYPES = _MESH_TYPES | _CURVE_TYPES | _POINT_TYPES

# segments used when flattening an analytical arc/circle/ellipse to a polyline.
# Blender has no native arc primitive, so these are tessellated on the way in.
_ARC_SEGMENTS = 64


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
    # container subtype -> how many CONTAINERs had no Blender mapping. Surfaced
    # instead of baking them as misleading empty collections.
    unmapped_containers: Dict[str, int] = field(default_factory=dict)

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


def _build_containers(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    result: BakeResult,
) -> Dict[int, bpy.types.Collection]:
    """Bake every CONTAINER axis to the documented Blender mapping.

    The spec's CONTAINER is polymorphic — its subtype picks the grouping axis,
    and each axis has its own membership relation. Blender has one grouping
    concept (the collection), but an object may live in many collections at
    once, which is exactly the multi-axis membership model:

    - ``Collection`` (IN_COLLECTION) — the authored tree, under the root.
    - ``Model`` (IN_MODEL) — the federation tier. One model maps onto the root;
      several become the outermost tier of collections, per the spec.
    - ``Group`` (IN_GROUP) — a ``Groups`` branch; objects multi-link in.
    - ``MEP System`` / ``Network`` (IN_SYSTEM) — a ``Systems`` branch, likewise.

    A subtype this mapping does not know is tallied on ``result`` and *not*
    baked — an empty folder would misread as "this grouping arrived intact".
    """
    created: Dict[int, bpy.types.Collection] = {}
    _build_collection_tree(bundle, root_collection, created)
    _build_model_tier(bundle, root_collection, created)
    _build_axis_branch(bundle, root_collection, created, {"Group"}, "Groups")
    _build_axis_branch(
        bundle, root_collection, created, {"MEP System", "Network"}, "Systems"
    )

    for container in bundle.containers.values():
        if container.node_id not in created:
            subtype = container.subtype or "(no subtype)"
            result.unmapped_containers[subtype] = (
                result.unmapped_containers.get(subtype, 0) + 1
            )
    return created


def _build_collection_tree(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Recreate the authored collection tree under ``root_collection``.

    The published root maps onto the caller's root rather than nesting inside it,
    so a load does not add a redundant folder level.
    """
    root_id = bundle.root_collection_id
    if root_id is not None:
        created[root_id] = root_collection

    def link_children(parent_id: Optional[int]) -> None:
        parent = created.get(parent_id, root_collection)
        for child in bundle.child_containers(parent_id):
            if not child.is_collection or child.node_id in created:
                continue
            collection = bpy.data.collections.new(child.name)
            parent.children.link(collection)
            created[child.node_id] = collection
            link_children(child.node_id)

    link_children(root_id)
    # Any collection not reachable from the root (a second parentless root, a
    # broken def_ref) still needs a home, or its objects would silently vanish.
    for node_id, child in bundle.containers.items():
        if child.is_collection and node_id not in created:
            collection = bpy.data.collections.new(child.name)
            root_collection.children.link(collection)
            created[node_id] = collection
            link_children(node_id)


def _build_model_tier(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
) -> None:
    """Bake CONTAINER(Model) — the federation's source-file grouping.

    A single model maps onto the caller's root, mirroring how a lone authored
    root does; a real federation gets one collection per model under the root,
    the spec's "outermost scene-view tier when >1 model".
    """
    models = sorted(
        (c for c in bundle.containers.values() if c.subtype == "Model"),
        key=lambda c: c.node_id,
    )
    if not models:
        return
    if len(models) == 1:
        created[models[0].node_id] = root_collection
        return
    for model in models:
        collection = bpy.data.collections.new(model.name)
        root_collection.children.link(collection)
        created[model.node_id] = collection


def _build_axis_branch(
    bundle: ReceivedBundle,
    root_collection: bpy.types.Collection,
    created: Dict[int, bpy.types.Collection],
    subtypes: set,
    branch_name: str,
) -> None:
    """Park one non-spatial grouping axis under a single branch collection.

    Groups and systems are membership *sets*, not a partition: an object keeps
    its authored collection and additionally links into each of these. Keeping
    the axis under one branch stops a Navis model's forty networks from reading
    as forty top-level folders. The branch only exists when the axis does, so a
    Blender-published bundle gains nothing.
    """
    members = {
        c.node_id: c for c in bundle.containers.values() if c.subtype in subtypes
    }
    if not members:
        return
    branch = bpy.data.collections.new(branch_name)
    root_collection.children.link(branch)

    def link(container, chain: frozenset) -> bpy.types.Collection:
        existing = created.get(container.node_id)
        if existing is not None:
            return existing
        # groups may nest via def_ref; a parent outside the axis (or a corrupt
        # def_ref cycle) tops out at the branch
        parent_container = members.get(container.parent_id)
        parent = branch
        if parent_container is not None and parent_container.node_id not in chain:
            parent = link(parent_container, chain | {container.node_id})
        collection = bpy.data.collections.new(container.name)
        parent.children.link(collection)
        created[container.node_id] = collection
        return collection

    for container in sorted(members.values(), key=lambda c: c.node_id):
        link(container, frozenset({container.node_id}))


def _decode_meshes(
    geometries: List[BundleGeometry],
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


def _decode_curves(geometries: List[BundleGeometry]) -> Tuple[List[object], List[str]]:
    """Decode the curve-family blobs of one object into Speckle objects.

    Curves go through the full ``decode`` rather than a raw fast path: they are
    orders of magnitude rarer than meshes, so the ``Base`` allocation that the
    mesh path deliberately avoids does not matter here, and the object model
    carries the NURBS definition we need to rebuild a real spline.
    """
    decoded: List[object] = []
    errors: List[str] = []
    for geometry in geometries:
        try:
            decoded.append(sgeo.decode(geometry.content))
        except sgeo.SgeoDecodeError as e:
            errors.append(str(e))
    return decoded, errors


def _curve_datablock(name: str, curves: List[object]) -> Optional[bpy.types.Curve]:
    """Merge one object's curve-family geometry into a single Curve data-block.

    A Blender Curve holds many splines, which is the direct parallel of merging
    several display meshes into one Mesh.
    """
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    for curve in curves:
        _add_splines(curve_data, curve)
    if not curve_data.splines:
        bpy.data.curves.remove(curve_data)
        return None
    return curve_data


def _add_splines(curve_data: bpy.types.Curve, curve) -> None:
    """Append the spline(s) one decoded curve-family object describes."""
    kind = type(curve).__name__

    if kind == "Polycurve":
        # a polycurve is a container; each segment contributes its own spline
        for segment in curve.segments:
            _add_splines(curve_data, segment)
        return

    scale = _scale_for(getattr(curve, "units", None))

    if kind == "Curve":
        _add_nurbs_spline(curve_data, curve, scale)
    elif kind == "Polyline":
        _add_poly_spline(curve_data, curve.value, _closed(curve), scale)
    elif kind == "Line":
        points = [
            curve.start.x,
            curve.start.y,
            curve.start.z,
            curve.end.x,
            curve.end.y,
            curve.end.z,
        ]
        _add_poly_spline(curve_data, points, False, scale)
    elif kind in ("Arc", "Circle", "Ellipse"):
        _add_poly_spline(curve_data, _tessellate(curve, kind), kind != "Arc", scale)
    elif kind == "Spiral":
        # a spiral has no closed form Blender can express; the producer's own
        # render polyline is the faithful reading
        display = curve["displayValue"] if "displayValue" in curve.keys() else None
        if display is not None and display.value:
            _add_poly_spline(curve_data, display.value, _closed(display), scale)


def _closed(curve) -> bool:
    """Read a curve's closed flag, whether it is a field or a dynamic member."""
    closed = getattr(curve, "closed", None)
    if closed is None and hasattr(curve, "keys") and "closed" in curve.keys():
        closed = curve["closed"]
    return bool(closed)


def _add_poly_spline(
    curve_data: bpy.types.Curve,
    values: List[float],
    closed: bool,
    scale: float,
) -> None:
    """Add a POLY spline from a flat xyz list."""
    count = len(values) // 3
    if count < 2:
        return
    spline = curve_data.splines.new("POLY")
    # a new spline already owns one point
    spline.points.add(count - 1)
    # Blender spline points are 4D (x, y, z, w)
    flat: List[float] = []
    for i in range(count):
        flat.extend(
            (
                values[i * 3] * scale,
                values[i * 3 + 1] * scale,
                values[i * 3 + 2] * scale,
                1.0,
            )
        )
    spline.points.foreach_set("co", flat)
    spline.use_cyclic_u = closed


def _add_nurbs_spline(curve_data: bpy.types.Curve, curve, scale: float) -> None:
    """Rebuild a NURBS spline from the analytical definition.

    Preferred over the render polyline because it comes back editable — the
    control points, degree and weights are exactly what the publish side read
    off the Blender spline. Falls back to the display polyline when the
    definition is too degenerate for Blender to accept.

    Known approximation: **Blender's Python API cannot set a NURBS knot
    vector.** It derives one from ``order_u`` / ``use_cyclic_u`` /
    ``use_endpoint_u``, so a source curve with non-uniform knots is redrawn on a
    uniform basis. Control points, degree and weights survive exactly; the
    traced path can drift. Measured against the producer's own render polyline
    on a 55-curve model: half the curves within 0.03%, 50 of 51 within 5%.
    """
    points = curve.points
    count = len(points) // 3
    if count < 2:
        display = getattr(curve, "displayValue", None)
        if display is not None:
            _add_poly_spline(curve_data, display.value, _closed(curve), scale)
        return

    spline = curve_data.splines.new("NURBS")
    spline.points.add(count - 1)
    weights = curve.weights if len(curve.weights) == count else [1.0] * count
    flat: List[float] = []
    for i in range(count):
        flat.extend(
            (
                points[i * 3] * scale,
                points[i * 3 + 1] * scale,
                points[i * 3 + 2] * scale,
                weights[i],
            )
        )
    spline.points.foreach_set("co", flat)
    # Blender's order is degree + 1 and may not exceed the control point count
    spline.order_u = max(2, min(curve.degree + 1, count))
    spline.use_cyclic_u = bool(curve.closed)
    # `periodic` is `not use_endpoint_u` on the publish side, but Blender writes
    # it from a field Bezier splines do not really have, so every Bezier arrives
    # claiming to be periodic. A clamped knot vector is the curve's own,
    # trustworthy statement that it interpolates its endpoints, so believe that
    # first and fall back to the flag only when the knots say nothing.
    spline.use_endpoint_u = _is_clamped(curve.knots, curve.degree) or not bool(
        curve.periodic
    )


def _is_clamped(knots: List[float], degree: int) -> bool:
    """True when the knot vector pins the curve to its first and last control point.

    The test is the standard one — the leading and trailing ``degree`` knots each
    repeated — with the added requirement that the two ends differ, which rejects
    the all-zero vectors some producers emit for degenerate curves.
    """
    if degree < 1 or len(knots) < 2 * degree:
        return False
    head, tail = knots[:degree], knots[-degree:]
    if head[0] == tail[0]:
        return False
    return all(k == head[0] for k in head) and all(k == tail[0] for k in tail)


def _tessellate(curve, kind: str) -> List[float]:
    """Flatten an analytical arc/circle/ellipse into a flat xyz list.

    Blender has no native arc primitive, so these become polylines. The plane's
    xdir/ydir give the parametrisation basis; an arc additionally has to pick
    the sweep direction that actually passes through its midpoint.
    """
    import math

    plane = curve.plane
    o, x, y = plane.origin, plane.xdir, plane.ydir

    def at(angle: float, rx: float, ry: float) -> Tuple[float, float, float]:
        cos, sin = math.cos(angle) * rx, math.sin(angle) * ry
        return (
            o.x + x.x * cos + y.x * sin,
            o.y + x.y * cos + y.y * sin,
            o.z + x.z * cos + y.z * sin,
        )

    def angle_of(point) -> float:
        dx = point.x - o.x, point.y - o.y, point.z - o.z
        u = dx[0] * x.x + dx[1] * x.y + dx[2] * x.z
        v = dx[0] * y.x + dx[1] * y.y + dx[2] * y.z
        return math.atan2(v, u)

    if kind == "Circle":
        radius = curve.radius
        start, sweep, rx, ry = 0.0, 2.0 * math.pi, radius, radius
    elif kind == "Ellipse":
        start, sweep = 0.0, 2.0 * math.pi
        rx, ry = curve.first_radius, curve.second_radius
    else:  # Arc
        radius = math.dist(
            (curve.startPoint.x, curve.startPoint.y, curve.startPoint.z),
            (o.x, o.y, o.z),
        )
        rx = ry = radius
        start = angle_of(curve.startPoint)
        end = angle_of(curve.endPoint)
        mid = angle_of(curve.midPoint)
        sweep = _arc_sweep(start, mid, end)

    values: List[float] = []
    # a closed conic repeats its first point implicitly via use_cyclic_u, so the
    # final sample is dropped; an arc keeps both endpoints
    steps = _ARC_SEGMENTS if kind != "Arc" else _ARC_SEGMENTS
    last = steps if kind == "Arc" else steps - 1
    for i in range(last + 1):
        values.extend(at(start + sweep * (i / steps), rx, ry))
    return values


def _arc_sweep(start: float, mid: float, end: float) -> float:
    """Signed sweep from ``start`` to ``end`` that passes through ``mid``.

    Three points do not say which way round the circle the arc goes, so the
    midpoint is what disambiguates — take the direction whose forward sweep
    reaches ``mid`` before ``end``.
    """
    import math

    tau = 2.0 * math.pi

    def forward(a: float, b: float) -> float:
        return (b - a) % tau

    if forward(start, mid) <= forward(start, end):
        return forward(start, end)
    return forward(start, end) - tau


def _points_object(name: str, points: List[object]) -> Optional[bpy.types.Object]:
    """Turn POINTS geometry into the Blender shape it came from.

    A single Point becomes an Empty — that is what Blender published it from —
    while a PointCloud becomes a vertex-only mesh, which is the only Blender
    data-block that holds many loose points.
    """
    coords: List[Tuple[float, float, float]] = []
    for point in points:
        scale = _scale_for(getattr(point, "units", None))
        if type(point).__name__ == "PointCloud":
            coords.extend((p.x * scale, p.y * scale, p.z * scale) for p in point.points)
        else:
            coords.append((point.x * scale, point.y * scale, point.z * scale))

    if not coords:
        return None
    if len(coords) == 1:
        empty = bpy.data.objects.new(name, None)
        empty.location = coords[0]
        return empty

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(coords, [], [])
    mesh.update()
    return bpy.data.objects.new(name, mesh)


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
    """Write the object's eav user properties back as Blender custom properties.

    Only the ``properties.`` subtree round-trips — the reader routes bare root
    scalars (``type`` and any cross-producer extras) into ``root_fields``, and
    those stay internal. ``applicationId`` and ``speckle_type`` are baked
    deliberately, matching the classic receive path; the publish side's
    ``extract_custom_properties`` skips both, so they do not re-enter
    ``properties.*`` on a republish.
    """
    blender_object["applicationId"] = obj.application_id
    if obj.speckle_type:
        blender_object["speckle_type"] = obj.speckle_type
    for path, value in obj.properties.items():
        key = path[len("properties.") :]
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
    containers = _build_containers(bundle, root_collection, result)

    definition_collections = _build_definitions(bundle, materials, result)

    for obj in bundle.objects:
        target = _primary_home(obj, containers, root_collection)

        if obj.is_placement:
            built = _bake_placement(
                obj, bundle, definition_collections, instance_loading_mode
            )
        else:
            built = _bake_object(obj, bundle, materials, result)

        if not built:
            continue

        # the primary carries the object's identity; extra parts only appear for
        # mixed-family objects and are already parented to it
        for part in built:
            if part.name not in target.objects:
                target.objects.link(part)
        # group / system memberships are additive, not a move: the object stays
        # in its spatial home and also appears in each grouping it belongs to
        for extra_id in obj.group_ids + obj.system_ids:
            extra = containers.get(extra_id)
            if extra is None or extra is target:
                continue
            for part in built:
                if part.name not in extra.objects:
                    extra.objects.link(part)
        _apply_properties(built[0], obj)
        result.objects[obj.application_id] = built[0]

    _parent_subelements(bundle, result)
    return result


def _primary_home(
    obj: BundleObject,
    containers: Dict[int, bpy.types.Collection],
    root_collection: bpy.types.Collection,
) -> bpy.types.Collection:
    """The collection an object's scene-tree entry lives in.

    The authored collection wins when the producer sent one; a federated object
    without one sits in its model's tier; anything else lands at the root.
    """
    for node_id in (obj.collection_id, obj.model_id):
        home = containers.get(node_id) if node_id is not None else None
        if home is not None:
            return home
    return root_collection


def _bake_object(
    obj: BundleObject,
    bundle: ReceivedBundle,
    materials: Dict[int, bpy.types.Material],
    result: BakeResult,
) -> List[bpy.types.Object]:
    """Bake one ordinary (non-placement) object into one or more data-blocks.

    A Blender object holds a single data-block, so when an object's display
    geometry spans families (a Revit wall with a mesh body and edge curves, say)
    the mesh wins the object itself and the rest become child objects. Blender's
    own publishes are always homogeneous, so this only fires cross-connector.

    Returns the objects to link, primary first, or ``[]`` when nothing could be
    built.
    """
    geometries = [
        bundle.geometries[k] for k in obj.geometry_ks if k in bundle.geometries
    ]
    if not geometries:
        # properties-only, e.g. a metaball sibling — a real object with no shape
        return [_empty_object(obj)]

    decodable = _partition_decodable(geometries, result)
    if not decodable:
        # Every display geometry needs a decoder we do not have. Drop the object
        # rather than leaving a shapeless placeholder behind — the per-type tally
        # is reported, and a reload once the decoder lands brings the shape in.
        return []

    return _objects_from_geometries(
        obj.name or obj.application_id,
        f"{obj.name or obj.application_id}.{obj.k}",
        decodable,
        bundle,
        materials,
        result,
        obj.application_id,
    )


def _member_objects(
    name: str,
    decodable: List[BundleGeometry],
    bundle: ReceivedBundle,
    materials: Dict[int, bpy.types.Material],
    result: BakeResult,
) -> List[bpy.types.Object]:
    """The same build, for one member of an instance definition."""
    return _objects_from_geometries(
        name, name, decodable, bundle, materials, result, name
    )


def _objects_from_geometries(
    name: str,
    data_name: str,
    decodable: List[BundleGeometry],
    bundle: ReceivedBundle,
    materials: Dict[int, bpy.types.Material],
    result: BakeResult,
    error_key: str,
) -> List[bpy.types.Object]:
    """Build one Blender object per geometry family present, primary first.

    ``name`` names the objects, ``data_name`` the data-blocks — scene objects
    want the readable name, data-blocks want a unique one.
    """
    mesh_geos = [g for g in decodable if g.type in _MESH_TYPES]
    curve_geos = [g for g in decodable if g.type in _CURVE_TYPES]
    point_geos = [g for g in decodable if g.type in _POINT_TYPES]

    def materials_for(
        geos: List[BundleGeometry],
    ) -> List[Optional[bpy.types.Material]]:
        return [materials.get(bundle.geometry_materials.get(g.k, -1)) for g in geos]

    def record(errors: List[str]) -> None:
        for error in errors:
            result.decode_errors.append((error_key, error))

    built: List[bpy.types.Object] = []

    if mesh_geos:
        meshes, errors = _decode_meshes(mesh_geos)
        record(errors)
        if meshes:
            data = _mesh_datablock(data_name, meshes, materials_for(mesh_geos))
            built.append(bpy.data.objects.new(name, data))

    if curve_geos:
        curves, errors = _decode_curves(curve_geos)
        record(errors)
        data = _curve_datablock(f"{data_name}.curves", curves) if curves else None
        if data is not None:
            for material in materials_for(curve_geos):
                if material is not None and material.name not in data.materials:
                    data.materials.append(material)
            built.append(bpy.data.objects.new(name, data))

    if point_geos:
        points, errors = _decode_curves(point_geos)
        record(errors)
        if points:
            point_object = _points_object(name, points)
            if point_object is not None:
                built.append(point_object)

    # extras only exist for mixed-family objects; parent them to the primary so
    # the scene tree still reads as one thing
    for extra in built[1:]:
        extra.parent = built[0]
    return built


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

            member_name = f"{name}.{ordinal}"
            for member in _member_objects(
                member_name, decodable, bundle, materials, result
            ):
                collection.objects.link(member)

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
) -> List[bpy.types.Object]:
    """A collection instance: an empty pointing at the definition's collection.

    The publish side removed the collection's ``instance_offset`` from the
    placement transform and baked each member's ``matrix_world`` as
    definition-local geometry, so the transform applies here with no pivot
    correction — Blender's own offset is zero on a collection we created.

    Returns the objects to link, primary first, like ``_bake_object`` — the
    caller owns collection membership, so linked-duplicate copies land in the
    model's collection alongside their parent rather than in the scene root.
    """
    instance = bundle.instances.get(obj.instance_id or -1)
    if instance is None or instance.def_ref is None:
        return []
    definition = definition_collections.get(instance.def_ref)
    if definition is None:
        return []

    name = obj.name or obj.application_id
    matrix = _placement_matrix(instance.transform, instance.units)
    if instance_loading_mode == "LINKED_DUPLICATES":
        return _duplicate_definition(name, definition, matrix, frozenset())

    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = definition
    empty.matrix_world = matrix
    return [empty]


def _duplicate_definition(
    name: str,
    definition: bpy.types.Collection,
    matrix: Matrix,
    expanding: frozenset,
) -> List[bpy.types.Object]:
    """Expand one placement into a parent empty plus copies of the members.

    A copy shares its member's data-block — that is the "linked" in linked
    duplicates. A nested placement is the one member that must NOT be copied
    as-is: the copy would still be a COLLECTION-instance empty, leaving the
    nesting instanced when the user asked for editable objects. It is rebuilt
    instead as a plain empty whose children are themselves expanded copies, so
    the mode holds all the way down.

    ``expanding`` carries the definitions on the current expansion stack; a
    self-referential bundle (impossible from a real publisher, cheap to guard)
    stops instead of recursing forever.

    Transforms parent-chain: matrices here are definition-local ``matrix_basis``
    values, and only the outermost call passes a world-space placement — its
    empty has no parent, so basis and world coincide.
    """
    parent = bpy.data.objects.new(name, None)
    parent.matrix_basis = matrix
    built = [parent]
    if definition.name in expanding:
        return built
    expanding = expanding | {definition.name}

    for member in definition.objects:
        if member.instance_type == "COLLECTION" and member.instance_collection:
            children = _duplicate_definition(
                member.name, member.instance_collection, member.matrix_basis, expanding
            )
            children[0].parent = parent
            built.extend(children)
        else:
            copy = member.copy()
            copy.parent = parent
            built.append(copy)
    return built


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
