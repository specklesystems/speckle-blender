"""Drives specklepy's ``BundleBuilder`` from a converted Blender scene.

Walks the root ``Collection`` returned by ``build_collection_hierarchy`` (Speckle
collections + ``BlenderObject``s with world-coordinate ``displayValue`` geometry,
plus the attached ``renderMaterialProxies``) and maps it onto the builder. The
builder owns interning, edge emission and the parquet write; this class owns
only the walk — the C# ``IBundleBuilder`` boundary: a connector's send is
exactly its conversion, and everything after it belongs to the SDK.

Blender uses the direct-display dialect (same as Rhino): an ordinary object's
``displayValue`` is already in world coordinates, so it links straight to
geometry with DISPLAY edges. The Blender collection tree becomes CONTAINER nodes
(subtype "Collection") joined by IN_COLLECTION edges, and the default scene view
groups by that relation.

Collection instances are the exception, and take the same DEFINITION/INSTANCE
layer the C# connectors use for blocks: the placement empty gets an INSTANCE node
(carrying the transform) reached by DISPLAY_INSTANCE, the instanced collection
gets a DEFINITION node, and the definition's members hang off it with DEFINES
(geometry) or a nested member placement (DEFINES_INSTANCE + DEFINES_MEMBER +
PLACES, the builder's shape). A member that renders only through a placement is
listed in the root's ``definitionOnlyObjects`` and gets no IN_COLLECTION or
DISPLAY of its own — otherwise it would also draw untransformed at its authored
location, duplicating the instance.

Reference implementation: ``RhinoBundleBuilder.cs`` in speckle-sharp-connectors.
"""

from typing import Any, Dict, List, Tuple

from specklepy.bundle.builder import (
    BundleBuilder,
    BundleContainer,
    BundleGeometry,
    BundleInstance,
)
from specklepy.bundle.envelope_writer import Producer, SceneViewKey
from specklepy.bundle.spec import Rel
from specklepy.objects.base import Base
from specklepy.objects.models.collections.collection import Collection
from specklepy.objects.proxies import InstanceProxy


def blender_producer() -> Producer:
    """Provenance stamped into ``meta.produced_by``/``producer_version``: the
    slug of the connector that wrote the bundle and the version of the Blender
    actually running, so a bundle self-describes the host that produced it.

    Deliberately *not* ``ADDON_INFO["blender"]`` — that is the minimum Blender
    the add-on supports (4.2.0), so every bundle claimed to come from 4.2.0
    regardless of the host. ``sdk_name``/``sdk_version`` are filled by
    ``Producer`` itself and cover the specklepy side.
    """
    # deferred: this module is a pure Base/Collection -> builder translator and
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
    """Translates a converted Blender root Collection onto a ``BundleBuilder``.

    The caller owns the builder's lifecycle: construct it, run
    :meth:`export`, then hand the builder to ``specklepy.bundle.send`` (or call
    ``builder.build()`` for an offline write).
    """

    def __init__(self, builder: BundleBuilder) -> None:
        self._builder = builder
        self._conversion_errors: List[Tuple[str, Exception]] = []
        # instancing, resolved in _prepare_instancing / used by _emit_definitions
        self._definitions: List[Base] = []
        self._definition_only: set = set()
        # a definition-only member's payload is deferred to _emit_definitions:
        # displayValue geometry for a plain member, the InstanceProxy for a
        # member that is itself a placement. Emitting it during the walk would
        # need a DISPLAY edge the member must not have.
        self._deferred_geometry: Dict[str, List[Base]] = {}
        self._deferred_placements: Dict[str, InstanceProxy] = {}
        # every standalone placement's INSTANCE handle, so a member selected in
        # its own right can still be linked into its definition
        self._placement_instances: Dict[str, BundleInstance] = {}
        # every written geometry handle by applicationId — display and
        # definition geometry both — so material proxies can bind to it
        self._geometry_handles: Dict[str, BundleGeometry] = {}
        # id() of every Collection that will actually hold a visible object
        self._collections_to_emit: set = set()

    def export(self, root: Collection) -> int:
        """Emit the whole scene onto the builder. Returns the object count."""
        self._prepare_instancing(root)
        self._walk_collection(root, parent=None, is_root=True)
        # after the walk: every member's geometry / nested placement must exist
        # before the edges that resolve them
        self._emit_definitions()
        self._emit_subelements(root)
        self._emit_materials(root)
        self._builder.scene_view(
            "Collections", True, SceneViewKey.rel(Rel.IN_COLLECTION)
        )
        return len(self._builder.objects)

    @property
    def conversion_errors(self) -> List[Tuple[str, Exception]]:
        """(applicationId, error) pairs for geometry that could not be encoded."""
        return self._conversion_errors

    # ── scene tree ──────────────────────────────────────────────────────────

    def _walk_collection(
        self,
        collection: Collection,
        parent: BundleContainer | None,
        is_root: bool = False,
    ) -> None:
        # A collection holding nothing but definition-only members contributes no
        # IN_COLLECTION edge, so emitting it would leave an empty folder in the
        # viewer's scene tree — the usual shape for an instanced "library"
        # collection excluded from the view layer. Skip the node but keep walking:
        # its members still need geometry and properties for DEFINES to resolve.
        if is_root or id(collection) in self._collections_to_emit:
            name = _attr(collection, "name") or "Collection"
            container = self._builder.get_or_add_container(
                _attr(collection, "applicationId") or name, name, parent, "Collection"
            )
        else:
            container = parent

        for element in _attr(collection, "elements", []) or []:
            if isinstance(element, Collection):
                self._walk_collection(element, container)
            else:
                self._emit_object(element, container)

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

    def _emit_object(self, obj: Base, container: BundleContainer) -> None:
        app_id = _attr(obj, "applicationId")
        if not app_id:
            return

        handle = self._builder.get_or_add_object(app_id)
        if handle.properties_written:
            # already emitted — an object appears in the tree once
            return
        handle.set_properties(
            _attr(obj, "properties", {}) or {},
            name=_attr(obj, "name"),
            speckle_type=getattr(obj, "speckle_type", None),
            source_type=_attr(obj, "type"),
        )

        # A definition-only member is reachable solely through a placement, so it
        # gets no scene-tree membership and no render edge — only the DEFINES that
        # _emit_definitions adds. Its properties still land here, which is what
        # lets a placement resolve to a named, queryable member.
        standalone = app_id not in self._definition_only
        if standalone:
            handle.collection = container

        if isinstance(obj, InstanceProxy):
            if standalone:
                definition = self._builder.get_or_add_definition(
                    obj.definitionId, None
                )
                self._placement_instances[app_id] = handle.place(
                    definition, obj.transform, _attr(obj, "units"), key=app_id
                )
            else:
                # a nested placement is reached through its definition instead
                self._deferred_placements[app_id] = obj
            return

        elements = list(_attr(obj, "displayValue", []) or [])
        if not standalone:
            self._deferred_geometry[app_id] = elements
            return
        for ord_, element in enumerate(elements):
            geo_id = _attr(element, "applicationId") or f"{app_id}:{ord_}"
            try:
                geometry = handle.add_geometry(element, geometry_key=geo_id)
            except ValueError as e:
                # geometry type without an SGEO mapping — skip it, keep the object
                self._conversion_errors.append((geo_id, e))
                continue
            self._geometry_handles[geo_id] = geometry

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
                self._builder.get_or_add_definition(def_id, _attr(proxy, "name"))

    def _emit_definitions(self) -> None:
        """Link each definition to its members.

        All of a member's geometry shares its member ordinal, which is what lets
        a consumer regroup the fragments into one member. A member that is
        itself a placement goes through ``add_member_placement`` (the builder's
        nested-instance shape); one that was independently selected already has
        its geometry written with DISPLAY edges and only gains DEFINES onto the
        same rows.
        """
        for proxy in self._definitions:
            def_id = _attr(proxy, "applicationId")
            if not def_id:
                continue
            definition = self._builder.get_or_add_definition(
                def_id, _attr(proxy, "name")
            )

            for member_ord, member_id in enumerate(_attr(proxy, "objects", []) or []):
                deferred = self._deferred_placements.get(member_id)
                if deferred is not None:
                    definition.add_member_placement(
                        self._builder.get_or_add_object(member_id),
                        self._builder.get_or_add_definition(
                            deferred.definitionId, None
                        ),
                        deferred.transform,
                        _attr(deferred, "units"),
                        member_ord,
                    )
                    continue

                placed = self._placement_instances.get(member_id)
                if placed is not None:
                    # a placement selected in its own right and also a member:
                    # its INSTANCE node exists, only the DEFINES_INSTANCE edge
                    # is missing (no builder verb reuses an existing instance)
                    self._builder.pipeline.defines_instance(
                        definition.k, placed.k, member_ord
                    )
                    continue

                member = self._builder.try_get_object(member_id)
                if member is not None and member.geometries:
                    for geometry in member.geometries:
                        definition.add_existing_geometry(geometry, member_ord)
                    continue

                for i, element in enumerate(self._deferred_geometry.get(member_id, [])):
                    geo_id = _attr(element, "applicationId") or f"{member_id}:{i}"
                    try:
                        geometry = definition.add_geometry(
                            element, geometry_key=geo_id, member_ord=member_ord
                        )
                    except ValueError as e:
                        self._conversion_errors.append((geo_id, e))
                        continue
                    self._geometry_handles[geo_id] = geometry

    # ── subelements ─────────────────────────────────────────────────────────

    def _emit_subelements(self, root: Collection) -> None:
        """Parent -> child SUBELEMENT edges from the root's ``subelementIds``.

        Currently only metaball families: the basis carries the merged blob and
        its siblings hang off it carrying properties. That inverts Revit's
        curtain wall — where the children own the geometry — but the edge is the
        same one, and ``RevitArtifactRootObjectBuilder.EmitChild`` is the model.

        Runs after the walk so both ends are already emitted with their
        properties, geometry and IN_COLLECTION edge. An end whose object never
        made it into the tree is skipped rather than interned into existence,
        which would leave a dangling edge.
        """
        subelements: Dict[str, List[str]] = _attr(root, "subelementIds", {}) or {}
        for parent_id, child_ids in subelements.items():
            parent = self._builder.try_get_object(parent_id)
            if parent is None:
                continue
            for ord_, child_id in enumerate(child_ids):
                child = self._builder.try_get_object(child_id)
                if child is None:
                    continue
                parent.add_child(child, ord_)

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
            handle = self._builder.get_or_add_material(
                mat_id,
                _attr(material, "name"),
                argb=int(_attr(material, "diffuse", -1)),
                opacity=float(_attr(material, "opacity", 1.0)),
                metalness=float(_attr(material, "metalness", 0.0)),
                roughness=float(_attr(material, "roughness", 1.0)),
            )
            for geo_id in _attr(proxy, "objects", []) or []:
                geometry = self._geometry_handles.get(geo_id)
                if geometry is not None:
                    # HAS_MATERIAL binds to geometry, not the object
                    geometry.material = handle
