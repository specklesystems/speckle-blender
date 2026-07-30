"""Sole geometry construction interface for bundle baking."""

from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix
from specklepy.bundle import sgeo

from ...bundle_reader import BundleGeometry, BundleObject, ReceivedBundle
from ..result import BakeResult
from ..transforms import recenter_origin, scale_for
from .curves import build_curve_object
from .mesh import build_mesh_object

# Geometry labels grouped by the Blender data-block they become. The order used
# below is load-bearing: mesh/box, then curves, then points.
_MESH_TYPES = frozenset({"mesh", "box"})
_CURVE_TYPES = frozenset(
    {"line", "polyline", "polycurve", "curve", "arc", "circle", "ellipse", "spiral"}
)
_POINT_TYPES = frozenset({"points"})
_DECODABLE_TYPES = _MESH_TYPES | _CURVE_TYPES | _POINT_TYPES


class GeometryBuilder:
    """Build ordinary bundle objects and instance-definition members."""

    def __init__(
        self,
        bundle: ReceivedBundle,
        materials: Dict[int, bpy.types.Material],
        result: BakeResult,
    ) -> None:
        self._bundle = bundle
        self._materials = materials
        self._result = result

    def build_object(self, obj: BundleObject) -> List[bpy.types.Object]:
        """Build one ordinary object, primary part first."""
        geometries = [
            self._bundle.geometries[k]
            for k in obj.geometry_ks
            if k in self._bundle.geometries
        ]
        if not geometries:
            # properties-only, e.g. a metaball sibling — a real object with no shape
            return [bpy.data.objects.new(obj.name or obj.application_id, None)]

        decodable = self._partition_decodable(geometries)
        if not decodable:
            # Entirely unsupported geometry is omitted, rather than represented
            # by a misleading shapeless placeholder.
            return []

        name = obj.name or obj.application_id
        return self._objects_from_geometries(
            name,
            f"{name}.{obj.k}",
            decodable,
            obj.application_id,
        )

    def build_definition_member(
        self, name: str, geometry_ids: List[int]
    ) -> List[bpy.types.Object]:
        """Build one definition member from its name and geometry identifiers."""
        geometries = [
            self._bundle.geometries[k]
            for k in geometry_ids
            if k in self._bundle.geometries
        ]
        decodable = self._partition_decodable(geometries)
        if not decodable:
            return []
        return self._objects_from_geometries(name, name, decodable, name)

    def _objects_from_geometries(
        self,
        name: str,
        data_name: str,
        decodable: List[BundleGeometry],
        error_key: str,
    ) -> List[bpy.types.Object]:
        """Build one Blender object per geometry family, primary first."""
        mesh_geos = [g for g in decodable if g.type in _MESH_TYPES]
        curve_geos = [g for g in decodable if g.type in _CURVE_TYPES]
        point_geos = [g for g in decodable if g.type in _POINT_TYPES]

        def materials_for(
            geos: List[BundleGeometry],
        ) -> List[Optional[bpy.types.Material]]:
            return [
                self._materials.get(self._bundle.geometry_materials.get(g.k, -1))
                for g in geos
            ]

        def record(errors: List[str]) -> None:
            for error in errors:
                self._result.decode_errors.append((error_key, error))

        built: List[bpy.types.Object] = []

        if mesh_geos:
            mesh_object, errors = build_mesh_object(
                name,
                data_name,
                mesh_geos,
                materials_for(mesh_geos),
            )
            record(errors)
            if mesh_object is not None:
                built.append(mesh_object)

        if curve_geos:
            curve_object, errors = build_curve_object(
                name,
                f"{data_name}.curves",
                curve_geos,
                materials_for(curve_geos),
            )
            record(errors)
            if curve_object is not None:
                built.append(curve_object)

        if point_geos:
            points, errors = _decode_points(point_geos)
            record(errors)
            if points:
                point_object = _points_object(name, points)
                if point_object is not None:
                    built.append(point_object)

        # Extras only exist for mixed-family objects. Recenter both endpoints
        # before parenting so every part's world-space geometry stays fixed.
        if len(built) > 1:
            for part in built:
                recenter_origin(part)
            primary_inverse = built[0].matrix_world.inverted(Matrix.Identity(4))
            for extra in built[1:]:
                extra.parent = built[0]
                extra.matrix_parent_inverse = primary_inverse
        return built

    def _partition_decodable(
        self, geometries: List[BundleGeometry]
    ) -> List[BundleGeometry]:
        """Keep supported geometry and tally unsupported blobs by type."""
        decodable: List[BundleGeometry] = []
        for geometry in geometries:
            if geometry.type in _DECODABLE_TYPES:
                decodable.append(geometry)
            else:
                self._result.skipped_by_type[geometry.type] = (
                    self._result.skipped_by_type.get(geometry.type, 0) + 1
                )
        return decodable


def _decode_points(
    geometries: List[BundleGeometry],
) -> Tuple[List[object], List[str]]:
    """Decode point-family blobs, collecting per-blob failures."""
    decoded: List[object] = []
    errors: List[str] = []
    for geometry in geometries:
        try:
            decoded.append(sgeo.decode(geometry.content))
        except sgeo.SgeoDecodeError as e:
            errors.append(str(e))
    return decoded, errors


def _points_object(name: str, points: List[object]) -> Optional[bpy.types.Object]:
    """Turn POINTS geometry into an Empty or a vertex-only Mesh."""
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
