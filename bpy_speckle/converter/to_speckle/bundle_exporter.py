"""Drives the Speckle 4.0 bundle producer from a converted Blender scene.

Walks the root ``Collection`` returned by ``build_collection_hierarchy`` (Speckle
collections + ``BlenderObject``s with world-coordinate ``displayValue`` geometry,
plus the attached ``renderMaterialProxies``) and maps it onto the parquet bundle
via ``ObjectsArtifactPipeline``.

Blender uses the direct-display dialect (same as Rhino): an ordinary object's
``displayValue`` is already in world coordinates, so it links straight to
geometry with DISPLAY edges. The Blender collection tree becomes CONTAINER nodes
(subtype "Collection") joined by IN_COLLECTION edges, and the default scene view
groups by that relation.

Collection instances are the exception, and take the same DEFINITION/INSTANCE
layer the C# connectors use for blocks: the placement empty gets an INSTANCE node
(carrying the transform) reached by DISPLAY_INSTANCE, the instanced collection
gets a DEFINITION node, and the definition's members hang off it with DEFINES
(geometry) or DEFINES_INSTANCE (a nested placement). A member that renders only
through a placement is listed in the root's ``definitionOnlyObjects`` and gets no
IN_COLLECTION or DISPLAY of its own — otherwise it would also draw untransformed
at its authored location, duplicating the instance.
"""

from typing import Any, Dict, List, Optional, Tuple

from specklepy.bundle.envelope_writer import Producer, SceneView, SceneViewKey
from specklepy.bundle.pipeline import ObjectsArtifactPipeline
from specklepy.bundle.spec import Rel
from specklepy.objects.base import Base
from specklepy.objects.models.collections.collection import Collection
from specklepy.objects.proxies import InstanceProxy


def _blender_producer() -> Producer:
    """Provenance stamped into ``meta.produced_by``/``producer_version``: the
    slug of the connector that wrote the bundle and the version of the Blender
    actually running, so a bundle self-describes the host that produced it.

    Deliberately *not* ``ADDON_INFO["blender"]`` — that is the minimum Blender
    the add-on supports (4.2.0), so every bundle claimed to come from 4.2.0
    regardless of the host. ``sdk_name``/``sdk_version`` are filled by
    ``Producer`` itself and cover the specklepy side.
    """
    # deferred: this module is a pure Base/Collection -> parquet translator and
    # keeps bpy out of its module-level imports; only provenance needs the host
    import bpy

    return Producer(slug="blender", version=".".join(map(str, bpy.app.version)))


def _attr(node: Base, key: str, default: Any = None) -> Any:
    """Read a typed or dynamic Base member, tolerating absence."""
    try:
        return node[key]
    except (KeyError, AttributeError):
        return getattr(node, key, default)


class BlenderBundleExporter:
    """Translates a converted Blender root Collection into a bundle on disk."""

    def __init__(
        self,
        output_dir: str,
        base_name: str,
        producer: Optional[Producer] = None,
    ) -> None:
        self._pipeline = ObjectsArtifactPipeline(
            output_dir, base_name, producer or _blender_producer()
        )
        self._base_name = base_name
        self._object_count = 0
        # geometry applicationIds actually written to the geometries table;
        # material edges may only reference these (an interned-but-unwritten K
        # would break the geometry K-space density the validator enforces).
        self._geo_k_by_id: Dict[str, int] = {}
        self._conversion_errors: List[Tuple[str, Exception]] = []
        # instancing, resolved in _prepare_instancing / used by _emit_definitions
        self._definitions: List[Base] = []
        self._definition_only: set = set()
        self._geo_ks_by_object: Dict[str, List[int]] = {}
        self._instance_k_by_object: Dict[str, int] = {}
        # applicationIds that actually reached the objects table, so a
        # SUBELEMENT edge can never point at an object that was never emitted
        self._emitted_object_ids: set = set()
        # id() of every Collection that will actually hold a visible object
        self._collections_to_emit: set = set()

    def export(self, root: Collection) -> Tuple[str, int]:
        """Emit the whole bundle. Returns ``(root_id, object_count)`` for the
        uploader."""
        self._prepare_instancing(root)
        self._walk_collection(root, parent_collection_k=None, is_root=True)
        # after the walk: every member's geometry / nested placement K must exist
        # before the edges that resolve them
        self._emit_definitions()
        self._emit_subelements(root)
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
        # A collection holding nothing but definition-only members contributes no
        # IN_COLLECTION edge, so emitting it would leave an empty folder in the
        # viewer's scene tree — the usual shape for an instanced "library"
        # collection excluded from the view layer. Skip the node but keep walking:
        # its members still need geometry and properties for DEFINES to resolve.
        if is_root or id(collection) in self._collections_to_emit:
            name = _attr(collection, "name") or "Collection"
            coll_k = self._pipeline.add_collection(
                _attr(collection, "applicationId") or name,
                name,
                parent_collection_k,
                "Collection",
            )
        else:
            coll_k = parent_collection_k

        for ord_, element in enumerate(_attr(collection, "elements", []) or []):
            if isinstance(element, Collection):
                self._walk_collection(element, coll_k)
            else:
                self._emit_object(element, coll_k, ord_)

    def _mark_collections_to_emit(self, collection: Collection) -> bool:
        """Record which collections hold something the scene tree will show.

        Returns True when this collection, or a descendant, contains an object
        that gets an IN_COLLECTION edge.
        """
        keep = False
        for element in _attr(collection, "elements", []) or []:
            if isinstance(element, Collection):
                # not short-circuited: every descendant has to be marked
                keep = self._mark_collections_to_emit(element) or keep
            else:
                app_id = _attr(element, "applicationId")
                if app_id and app_id not in self._definition_only:
                    keep = True

        if keep:
            self._collections_to_emit.add(id(collection))
        return keep

    def _emit_object(self, obj: Base, collection_k: int, ord_: int) -> None:
        app_id = _attr(obj, "applicationId")
        if not app_id:
            return

        obj_k = self._pipeline.intern_object(app_id)
        self._object_count += 1
        self._emitted_object_ids.add(app_id)
        self._pipeline.add_properties(
            app_id,
            _attr(obj, "properties", {}) or {},
            root_scalars=[
                ("name", _attr(obj, "name")),
                ("type", _attr(obj, "type")),
                ("speckle_type", getattr(obj, "speckle_type", None)),
            ],
        )

        # A definition-only member is reachable solely through a placement, so it
        # gets no scene-tree membership and no render edge — only the DEFINES that
        # _emit_definitions adds. Its properties and geometry still land, which is
        # what lets a placement resolve to real geometry.
        standalone = app_id not in self._definition_only
        if standalone:
            self._pipeline.in_collection(obj_k, collection_k, ord_)

        if isinstance(obj, InstanceProxy):
            self._emit_placement(obj, obj_k, app_id, standalone)
            return

        display_ord = 0
        geo_ks: List[int] = []
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
            if standalone:
                self._pipeline.display(obj_k, geo_k, display_ord)
            geo_ks.append(geo_k)
            display_ord += 1

        self._geo_ks_by_object[app_id] = geo_ks

    # ── instancing ──────────────────────────────────────────────────────────

    def _prepare_instancing(self, root: Collection) -> None:
        """Read the instancing tables off the root and pre-create DEFINITION nodes.

        Pre-creating them is what gives a definition its name: the per-object pass
        only ever sees a placement's ``definitionId``, so a lazily created node
        would be nameless. Same ordering as the Rhino artefact builder.
        """
        self._definitions = list(_attr(root, "instanceDefinitionProxies", []) or [])
        self._definition_only = set(_attr(root, "definitionOnlyObjects", []) or [])
        self._mark_collections_to_emit(root)

        for proxy in self._definitions:
            def_id = _attr(proxy, "applicationId")
            if def_id:
                self._pipeline.add_definition(def_id, _attr(proxy, "name"))

    def _emit_placement(
        self, proxy: InstanceProxy, obj_k: int, app_id: str, standalone: bool
    ) -> None:
        """A collection instance: object -> INSTANCE node -> DEFINITION."""
        def_k = self._pipeline.add_definition(proxy.definitionId, None)
        instance_k = self._pipeline.add_instance(
            app_id, def_k, proxy.transform, _attr(proxy, "units")
        )
        self._instance_k_by_object[app_id] = instance_k
        if standalone:
            # a nested placement is reached through DEFINES_INSTANCE instead
            self._pipeline.display_instance(obj_k, instance_k, 0)

    def _emit_definitions(self) -> None:
        """Link each definition to its members: DEFINES for geometry members,
        DEFINES_INSTANCE for members that are themselves placements."""
        for proxy in self._definitions:
            def_id = _attr(proxy, "applicationId")
            if not def_id:
                continue
            def_k = self._pipeline.add_definition(def_id, _attr(proxy, "name"))

            for member_ord, member_id in enumerate(_attr(proxy, "objects", []) or []):
                nested_k = self._instance_k_by_object.get(member_id)
                if nested_k is not None:
                    self._pipeline.defines_instance(def_k, nested_k, member_ord)
                    continue
                # all of a member's geometry shares its member ordinal, so a
                # consumer can group the fragments back into one member
                for geo_k in self._geo_ks_by_object.get(member_id, []):
                    self._pipeline.defines(def_k, geo_k, member_ord)

    # ── subelements ─────────────────────────────────────────────────────────

    def _emit_subelements(self, root: Collection) -> None:
        """Parent -> child SUBELEMENT edges from the root's ``subelementIds``.

        Currently only metaball families: the basis carries the merged blob and
        its siblings hang off it carrying properties. That inverts Revit's
        curtain wall — where the children own the geometry — but the edge is the
        same one, and ``RevitArtifactRootObjectBuilder.EmitChild`` is the model.

        Runs after the walk so both ends are already interned with their
        properties, geometry and IN_COLLECTION edge. ``intern_object`` is
        idempotent, so resolving a K here never creates a second object; a child
        whose object never made it into the tree is skipped rather than interned
        into existence, which would leave a dangling edge.
        """
        subelements: Dict[str, List[str]] = _attr(root, "subelementIds", {}) or {}
        for parent_id, child_ids in subelements.items():
            if parent_id not in self._emitted_object_ids:
                continue
            parent_k = self._pipeline.intern_object(parent_id)
            for ord_, child_id in enumerate(child_ids):
                if child_id not in self._emitted_object_ids:
                    continue
                child_k = self._pipeline.intern_object(child_id)
                self._pipeline.subelement(parent_k, child_k, ord_)

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
                name=_attr(material, "name"),
            )
            for geo_id in _attr(proxy, "objects", []) or []:
                geo_k = self._geo_k_by_id.get(geo_id)
                if geo_k is not None:
                    self._pipeline.has_material(geo_k, mat_k)
