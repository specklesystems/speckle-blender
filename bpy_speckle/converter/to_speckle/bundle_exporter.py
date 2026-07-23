"""Drives the Speckle 4.0 bundle producer from a converted Blender scene.

Walks the root ``Collection`` returned by ``build_collection_hierarchy`` (Speckle
collections + ``BlenderObject``s with world-coordinate ``displayValue`` geometry,
plus the attached ``renderMaterialProxies``) and maps it onto the parquet bundle
via ``ObjectsArtifactPipeline``.

Blender uses the direct-display dialect (same as Rhino): every ``displayValue``
element is already in world coordinates, so objects link straight to geometry
with DISPLAY edges — no DEFINITION/INSTANCE layer. The Blender collection tree
becomes CONTAINER nodes (subtype "Collection") joined by IN_COLLECTION edges,
and the default scene view groups by that relation.
"""

from typing import Any, Dict, List, Optional, Tuple

from specklepy.bundle.envelope_writer import SceneView, SceneViewKey
from specklepy.bundle.pipeline import ObjectsArtifactPipeline
from specklepy.bundle.spec import Rel
from specklepy.objects.base import Base
from specklepy.objects.models.collections.collection import Collection


def _attr(node: Base, key: str, default: Any = None) -> Any:
    """Read a typed or dynamic Base member, tolerating absence."""
    try:
        return node[key]
    except (KeyError, AttributeError):
        return getattr(node, key, default)


class BlenderBundleExporter:
    """Translates a converted Blender root Collection into a bundle on disk."""

    def __init__(self, output_dir: str, base_name: str) -> None:
        self._pipeline = ObjectsArtifactPipeline(output_dir, base_name)
        self._base_name = base_name
        self._object_count = 0
        # geometry applicationIds actually written to the geometries table;
        # material edges may only reference these (an interned-but-unwritten K
        # would break the geometry K-space density the validator enforces).
        self._geo_k_by_id: Dict[str, int] = {}
        self._conversion_errors: List[Tuple[str, Exception]] = []

    def export(self, root: Collection) -> Tuple[str, int]:
        """Emit the whole bundle. Returns ``(root_id, object_count)`` for the
        uploader."""
        self._walk_collection(root, parent_collection_k=None, is_root=True)
        self._emit_materials(root)
        self._pipeline.add_scene_view(
            SceneView(
                view=0,
                name="Collections",
                is_default=True,
                keys=[SceneViewKey.rel(Rel.IN_COLLECTION)],
            )
        )
        self._pipeline.complete()
        # deterministic synthetic root id, matching the C# connectors' convention
        return f"binary-{self._base_name}", self._object_count

    @property
    def conversion_errors(self) -> List[Tuple[str, Exception]]:
        """(applicationId, error) pairs for geometry that could not be encoded."""
        return self._conversion_errors

    # ── scene tree ──────────────────────────────────────────────────────────

    def _walk_collection(
        self,
        collection: Collection,
        parent_collection_k: Optional[int],
        is_root: bool = False,
    ) -> None:
        name = _attr(collection, "name") or "Collection"
        coll_k = self._pipeline.add_collection(
            _attr(collection, "applicationId") or name,
            name,
            parent_collection_k,
            "Collection",
        )
        for ord_, element in enumerate(_attr(collection, "elements", []) or []):
            if isinstance(element, Collection):
                self._walk_collection(element, coll_k)
            else:
                self._emit_object(element, coll_k, ord_)

    def _emit_object(self, obj: Base, collection_k: int, ord_: int) -> None:
        app_id = _attr(obj, "applicationId")
        if not app_id:
            return

        obj_k = self._pipeline.intern_object(app_id)
        self._object_count += 1
        self._pipeline.add_properties(
            app_id,
            _attr(obj, "properties", {}) or {},
            root_scalars=[
                ("name", _attr(obj, "name")),
                ("type", _attr(obj, "type")),
                ("speckle_type", getattr(obj, "speckle_type", None)),
            ],
        )
        self._pipeline.in_collection(obj_k, collection_k, ord_)

        display_ord = 0
        for element in _attr(obj, "displayValue", []) or []:
            geo_id = _attr(element, "applicationId") or f"{app_id}:{display_ord}"
            try:
                geo_k = self._geo_k_by_id.get(geo_id)
                if geo_k is None:
                    geo_k = self._pipeline.add_geometry(geo_id, element)
                    self._geo_k_by_id[geo_id] = geo_k
            except ValueError as e:
                # geometry type without an SGEO mapping — skip it, keep the object
                self._conversion_errors.append((geo_id, e))
                continue
            self._pipeline.display(obj_k, geo_k, display_ord)
            display_ord += 1

    # ── materials ───────────────────────────────────────────────────────────

    def _emit_materials(self, root: Collection) -> None:
        for proxy in _attr(root, "renderMaterialProxies", []) or []:
            material = _attr(proxy, "value")
            if material is None:
                continue
            mat_id = (
                _attr(proxy, "applicationId")
                or _attr(material, "applicationId")
                or _attr(material, "name")
                or ""
            )
            mat_k = self._pipeline.add_material(
                mat_id,
                argb=int(_attr(material, "diffuse", -1)),
                opacity=float(_attr(material, "opacity", 1.0)),
                metalness=float(_attr(material, "metalness", 0.0)),
                roughness=float(_attr(material, "roughness", 1.0)),
            )
            for geo_id in _attr(proxy, "objects", []) or []:
                geo_k = self._geo_k_by_id.get(geo_id)
                if geo_k is not None:
                    self._pipeline.has_material(geo_k, mat_k)
