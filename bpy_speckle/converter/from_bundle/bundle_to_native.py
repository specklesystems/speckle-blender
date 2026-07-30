"""Bakes a parsed bundle straight into Blender data-blocks.

The direct-bake receive path, modelled on Rhino's ``IArtifactHostObjectBuilder``:
parquet arrays go to ``bpy.data`` without ever being reconstituted into a Speckle
``Base`` graph. Publishing already wrote world-baked geometry (Blender's
direct-display dialect), so a mesh's coordinates are final — the object is
created at the origin with the mesh carrying its own world position, exactly
inverting ``mesh_to_speckle_meshes``. Objects that join a parent relationship
(SUBELEMENT hierarchies, mixed-family extras) are recentred onto their geometry
(``_recenter_origin``), world position unchanged, so viewport relationship
lines don't all converge on the origin.

Collection instances are the one exception, as they are on the publish side: an
INSTANCE node becomes an empty with ``instance_type = 'COLLECTION'`` pointing at
the definition's collection, and the placement transform goes on the empty.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix
from specklepy.bundle import sgeo
from ._baking.containers import build_containers, link_object_parts
from ._baking.materials import build_materials
from ._baking.properties import apply_properties
from ._baking.result import BakeResult
from ._baking.transforms import (
    origin_median,
    placement_matrix,
    recenter_origin,
    scale_for,
)
from .bundle_reader import (
    BundleGeometry,
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

    scale = scale_for(getattr(curve, "units", None))

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
        display = getattr(curve, "displayValue", None)
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
        scale = scale_for(getattr(point, "units", None))
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

    materials = build_materials(bundle)
    containers = build_containers(bundle, root_collection, result)

    definition_collections = _build_definitions(bundle, materials, result)

    for obj in bundle.objects:
        if obj.is_placement:
            built = _bake_placement(
                obj, bundle, definition_collections, instance_loading_mode
            )
        else:
            built = _bake_object(obj, bundle, materials, result)

        if not built:
            continue

        link_object_parts(obj, built, containers, root_collection)
        apply_properties(built[0], obj, result)
        result.objects[obj.application_id] = built[0]

    _parent_subelements(bundle, result)
    return result


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
    # the scene tree still reads as one thing. Both endpoints get a real origin
    # first, and the primary's fresh placement is inverted back out so the
    # extras' world-space data stays put.
    if len(built) > 1:
        for part in built:
            recenter_origin(part)
        primary_inverse = built[0].matrix_world.inverted(Matrix.Identity(4))
        for extra in built[1:]:
            extra.parent = built[0]
            extra.matrix_parent_inverse = primary_inverse
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
            empty.matrix_world = placement_matrix(instance.transform, instance.units)
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

    One object can carry several placements: Revit atomizes a family instance
    into one DEFINITION/INSTANCE pair per material, so a chair arrives as a
    cushions placement plus a frame placement. Every placement bakes; the
    extras parent to the primary so the Outliner still reads as one element.
    Each empty keeps its own world transform — the atoms of one element share
    a transform in practice, but the bundle does not promise it, so parenting
    must not re-interpret the extras' matrices as primary-local.

    Returns the objects to link, primary first, like ``_bake_object`` — the
    caller owns collection membership, so linked-duplicate copies land in the
    model's collection alongside their parent rather than in the scene root.
    """
    name = obj.name or obj.application_id
    built: List[bpy.types.Object] = []
    for instance_id in obj.instance_ids:
        instance = bundle.instances.get(instance_id)
        if instance is None or instance.def_ref is None:
            continue
        definition = definition_collections.get(instance.def_ref)
        if definition is None:
            continue
        matrix = placement_matrix(instance.transform, instance.units)
        if instance_loading_mode == "LINKED_DUPLICATES":
            built.extend(_duplicate_definition(name, definition, matrix, frozenset()))
        else:
            empty = bpy.data.objects.new(name, None)
            empty.instance_type = "COLLECTION"
            empty.instance_collection = definition
            empty.matrix_world = matrix
            built.append(empty)

    # only batch roots are unparented here — linked-duplicate members already
    # hang off their own batch root with definition-local matrices
    primary_inverse = None
    for extra in built[1:]:
        if extra.parent is not None:
            continue
        if primary_inverse is None:
            primary_inverse = built[0].matrix_world.inverted(Matrix.Identity(4))
        extra.parent = built[0]
        extra.matrix_parent_inverse = primary_inverse
    return built


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
            # a mixed-family extra carries the parent inverse from its
            # in-definition parenting; under the batch root its basis alone is
            # the definition-local matrix
            copy.matrix_parent_inverse = Matrix.Identity(4)
            built.append(copy)
    return built


def _parent_subelements(bundle: ReceivedBundle, result: BakeResult) -> None:
    """Re-establish SUBELEMENT parenting once every object exists.

    Revit family subelements with geometry can be independent placements whose
    matrices are already world-space, so assigning a parent must not apply the
    parent's placement a second time. Properties-only siblings have no spatial
    placement of their own and remain identity-local so they follow their owner,
    matching the original metaball-family behaviour.

    Both endpoints of every link get a meaningful origin first (see
    ``_recenter_origin``) — Blender draws relationship lines origin-to-origin,
    so world-baked endpoints left at the origin would each draw a line across
    the whole scene. A properties-only parent has no geometry to recentre onto
    and moves to the median of its placed children instead, taking its
    identity-local followers with it. A median-placed parent is *anchored*: if
    a later iteration links it as somebody's child, its world is preserved like
    a placed child's — following the new owner would drag the children already
    restored under it.
    """
    objects_by_id = bundle.objects_by_id()
    anchored: set = set()
    for obj in bundle.objects:
        if not obj.subelement_ids:
            continue
        parent = result.objects.get(obj.application_id)
        if parent is None:
            continue

        placed: List[Tuple[bpy.types.Object, Matrix]] = []
        followers: List[bpy.types.Object] = []
        for child_id in obj.subelement_ids:
            child = result.objects.get(child_id)
            if child is None or child is parent:
                continue
            child_obj = objects_by_id.get(child_id)
            if child in anchored or (
                child_obj and (child_obj.is_placement or child_obj.geometry_ks)
            ):
                recenter_origin(child)
                placed.append((child, child.matrix_world.copy()))
            else:
                followers.append(child)

        # the parent's origin must be final before any child is linked: a
        # child's world restore resolves against the parent's stored matrix
        recenter_origin(parent)
        if not obj.is_placement and not obj.geometry_ks and placed:
            parent.matrix_world = Matrix.Translation(
                origin_median([world.to_translation() for _, world in placed])
            )
            anchored.add(parent)

        for child, world_matrix in placed:
            child.parent = parent
            child.matrix_world = world_matrix
        for child in followers:
            child.parent = parent
