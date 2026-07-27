"""Reads a downloaded parquet bundle into plain dataclasses.

The inverse of ``BlenderBundleExporter``, and the read half of the 4.0 receive
path. Deliberately free of ``bpy``: everything here is parquet joins, so it runs
in the harness against a bundle directory with no Blender, no server and no
account. ``bundle_to_native`` turns the result into data-blocks.

The bundle stores interned indices, not names, and the indices live in three
separate K-spaces that must not be confused:

- **object K** — a row in ``eav.objects``; ``application_id`` is the join key.
- **geometry K** — a row in ``geometries``; carries the SGEO blob.
- **node id** — a row in ``envelope.nodes``; CONTAINER / DEFINITION / INSTANCE /
  MATERIAL all share this space, discriminated by ``kind``.

Relations then cross the spaces, and which space each end lives in depends
entirely on the relation type — ``DISPLAY`` is object K -> geometry K, while
``IN_COLLECTION`` is object K -> node id. Resolving an edge against the wrong
table silently yields a plausible-looking wrong answer, so every lookup here
goes through the space's own dict.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BundleGeometry:
    """One row of the geometries table — an opaque blob plus its type label."""

    k: int
    content: bytes
    # the SGEO primitive name the producer wrote: "mesh", "curve", "line", …
    type: str


@dataclass
class BundleMaterial:
    node_id: int
    name: Optional[str]
    argb: int
    opacity: float
    metalness: float
    roughness: float


@dataclass
class BundleCollection:
    node_id: int
    name: str
    # a CONTAINER's parent is a node field (def_ref), not a relation
    parent_id: Optional[int]


@dataclass
class BundleInstance:
    """An INSTANCE node: a placement of a definition at a transform."""

    node_id: int
    def_ref: Optional[int]
    # 16 row-major doubles, or empty when the producer wrote none
    transform: List[float]
    units: Optional[str]


@dataclass
class BundleDefinition:
    node_id: int
    name: Optional[str]
    # member ordinal -> the geometry Ks that member owns. All of one member's
    # geometry shares its ordinal, which is what lets fragments regroup.
    members: Dict[int, List[int]] = field(default_factory=dict)
    # member ordinal -> a nested INSTANCE node id (a placement inside a definition)
    nested: Dict[int, int] = field(default_factory=dict)


@dataclass
class BundleObject:
    k: int
    application_id: str
    name: Optional[str] = None
    speckle_type: Optional[str] = None
    # user properties, keyed by their flattened eav path ("properties.foo.bar")
    properties: Dict[str, Any] = field(default_factory=dict)
    # DISPLAY targets in ord order
    geometry_ks: List[int] = field(default_factory=list)
    # the CONTAINER node this object sits in, via IN_COLLECTION
    collection_id: Optional[int] = None
    # the INSTANCE node this object places, via DISPLAY_INSTANCE
    instance_id: Optional[int] = None
    # SUBELEMENT children, in ord order, as application_ids
    subelement_ids: List[str] = field(default_factory=list)

    @property
    def is_placement(self) -> bool:
        return self.instance_id is not None


@dataclass
class ReceivedBundle:
    """A whole bundle, joined back into names and cross-referenced objects."""

    schema_version: Optional[int] = None
    objects: List[BundleObject] = field(default_factory=list)
    geometries: Dict[int, BundleGeometry] = field(default_factory=dict)
    collections: Dict[int, BundleCollection] = field(default_factory=dict)
    materials: Dict[int, BundleMaterial] = field(default_factory=dict)
    instances: Dict[int, BundleInstance] = field(default_factory=dict)
    definitions: Dict[int, BundleDefinition] = field(default_factory=dict)
    # geometry K -> MATERIAL node id (HAS_MATERIAL binds to geometry, not object)
    geometry_materials: Dict[int, int] = field(default_factory=dict)

    @property
    def root_collection_id(self) -> Optional[int]:
        """The one CONTAINER with no parent — the published root collection."""
        for node_id, collection in self.collections.items():
            if collection.parent_id is None:
                return node_id
        return None

    def objects_by_id(self) -> Dict[str, BundleObject]:
        return {obj.application_id: obj for obj in self.objects}

    def child_collections(self, parent_id: Optional[int]) -> List[BundleCollection]:
        return [c for c in self.collections.values() if c.parent_id == parent_id]


def _read(bundle_dir: str, suffix: str) -> Optional[Dict[str, List[Any]]]:
    """Read one bundle table as columns, or None when it is absent.

    Tables are named ``<version_id>.<table>.parquet`` and the version id is only
    known at publish time, so match on the suffix.
    """
    import pyarrow.parquet as pq

    matches = glob.glob(os.path.join(bundle_dir, f"*.{suffix}.parquet"))
    if not matches:
        return None
    return pq.read_table(matches[0]).to_pydict()


def _read_geometries(bundle_dir: str) -> Dict[int, BundleGeometry]:
    """Read every geometry shard.

    Unlike the other tables, geometries can be sharded: shard 0 keeps the plain
    ``{base}.geometries.parquet`` name and overflow shards are
    ``{base}.geometries.{N}.parquet``. Reading only shard 0 would silently drop
    geometry on any model over ~1.5 GiB, so glob the whole set.
    """
    import pyarrow.parquet as pq

    geometries: Dict[int, BundleGeometry] = {}
    for path in sorted(glob.glob(os.path.join(bundle_dir, "*.geometries*.parquet"))):
        table = pq.read_table(path).to_pydict()
        for i, k in enumerate(table["geometryIndex"]):
            content = table["content"][i]
            if content is None:
                continue
            geometries[k] = BundleGeometry(
                k=k,
                content=bytes(content),
                type=table["type"][i] or "unknown",
            )
    return geometries


def _eav_value(rows: Dict[str, List[Any]], i: int) -> Any:
    """Pick the populated value column for one eav row.

    Numbers land in both ``value_string`` and ``value_double``; the double is the
    truer reading, so it wins. (This is why an int published as 42 reads back
    as 42.0 — the eav table has no integer column.)
    """
    if rows["value_double"][i] is not None:
        return rows["value_double"][i]
    if rows["value_boolean"][i] is not None:
        return rows["value_boolean"][i]
    return rows["value_string"][i]


def _parse_transform(transform: Optional[str]) -> List[float]:
    """Parse a row-major 4x4 stored as a CSV string; [] when malformed."""
    if not transform:
        return []
    try:
        values = [float(v) for v in transform.split(",")]
    except ValueError:
        return []
    return values if len(values) == 16 else []


def read_bundle(bundle_dir: str) -> ReceivedBundle:
    """Join a bundle directory back into a :class:`ReceivedBundle`."""
    bundle = ReceivedBundle()

    meta = _read(bundle_dir, "envelope.meta")
    if meta and meta.get("schema_version"):
        bundle.schema_version = meta["schema_version"][0]

    bundle.geometries = _read_geometries(bundle_dir)

    objects = _read(bundle_dir, "eav.objects") or {
        "object_index": [],
        "application_id": [],
    }
    by_k: Dict[int, BundleObject] = {}
    for i, k in enumerate(objects["object_index"]):
        by_k[k] = BundleObject(k=k, application_id=objects["application_id"][i])
    bundle.objects = [by_k[k] for k in sorted(by_k)]

    _read_nodes(bundle_dir, bundle)
    _read_relations(bundle_dir, bundle, by_k)
    _read_properties(bundle_dir, by_k)
    return bundle


def _read_nodes(bundle_dir: str, bundle: ReceivedBundle) -> None:
    """Split the nodes table into the four kinds that share its id space."""
    kinds = _read(bundle_dir, "envelope.node_kinds") or {"kind": [], "name": []}
    kind_name = dict(zip(kinds["kind"], kinds["name"]))

    nodes = _read(bundle_dir, "envelope.nodes")
    if not nodes:
        return

    for i, node_id in enumerate(nodes["id"]):
        name = kind_name.get(nodes["kind"][i])
        if name == "CONTAINER":
            bundle.collections[node_id] = BundleCollection(
                node_id=node_id,
                name=nodes["name"][i] or f"Collection_{node_id}",
                parent_id=nodes["def_ref"][i],
            )
        elif name == "DEFINITION":
            bundle.definitions[node_id] = BundleDefinition(
                node_id=node_id, name=nodes["name"][i]
            )
        elif name == "INSTANCE":
            bundle.instances[node_id] = BundleInstance(
                node_id=node_id,
                def_ref=nodes["def_ref"][i],
                transform=_parse_transform(nodes["transform"][i]),
                units=nodes["units"][i],
            )
        elif name == "MATERIAL":
            bundle.materials[node_id] = BundleMaterial(
                node_id=node_id,
                name=nodes["name"][i],
                argb=nodes["argb"][i] if nodes["argb"][i] is not None else -1,
                opacity=_or(nodes["opacity"][i], 1.0),
                metalness=_or(nodes["metalness"][i], 0.0),
                roughness=_or(nodes["roughness"][i], 1.0),
            )


def _or(value: Optional[float], fallback: float) -> float:
    return fallback if value is None else float(value)


def _read_relations(
    bundle_dir: str, bundle: ReceivedBundle, by_k: Dict[int, BundleObject]
) -> None:
    """Resolve every edge, each against the K-space its ends actually live in."""
    rel_types = _read(bundle_dir, "envelope.rel_types") or {"rel": [], "name": []}
    rel_name = dict(zip(rel_types["rel"], rel_types["name"]))

    relations = _read(bundle_dir, "envelope.relations")
    if not relations:
        return

    # ord is nullable, and sorting has to be stable for a missing one
    def ordinal(i: int) -> int:
        value = relations["ord"][i]
        return 0 if value is None else value

    display: Dict[int, List[Tuple[int, int]]] = {}
    subelements: Dict[int, List[Tuple[int, int]]] = {}

    for i, rel in enumerate(relations["rel"]):
        name = rel_name.get(rel)
        src, dst = relations["src"][i], relations["dst"][i]

        if name == "DISPLAY":
            # object K -> geometry K
            if src in by_k and dst in bundle.geometries:
                display.setdefault(src, []).append((ordinal(i), dst))

        elif name == "IN_COLLECTION":
            # object K -> CONTAINER node id
            if src in by_k and dst in bundle.collections:
                by_k[src].collection_id = dst

        elif name == "DISPLAY_INSTANCE":
            # object K -> INSTANCE node id
            if src in by_k and dst in bundle.instances:
                by_k[src].instance_id = dst

        elif name == "SUBELEMENT":
            # object K -> object K
            if src in by_k and dst in by_k:
                subelements.setdefault(src, []).append((ordinal(i), dst))

        elif name == "DEFINES":
            # DEFINITION node id -> geometry K, grouped by member ordinal
            definition = bundle.definitions.get(src)
            if definition is not None and dst in bundle.geometries:
                definition.members.setdefault(ordinal(i), []).append(dst)

        elif name == "DEFINES_INSTANCE":
            # DEFINITION node id -> nested INSTANCE node id
            definition = bundle.definitions.get(src)
            if definition is not None and dst in bundle.instances:
                definition.nested[ordinal(i)] = dst

        elif name == "HAS_MATERIAL":
            # geometry K -> MATERIAL node id. Bound to geometry, not object, so
            # one object's two display meshes can carry different materials.
            if src in bundle.geometries and dst in bundle.materials:
                bundle.geometry_materials[src] = dst

    for obj_k, pairs in display.items():
        by_k[obj_k].geometry_ks = [geo_k for _, geo_k in sorted(pairs)]

    for obj_k, pairs in subelements.items():
        by_k[obj_k].subelement_ids = [
            by_k[child_k].application_id for _, child_k in sorted(pairs)
        ]


def _read_properties(bundle_dir: str, by_k: Dict[int, BundleObject]) -> None:
    """Fold the eav rows back onto their objects.

    ``name`` / ``type`` / ``speckle_type`` were written as bare root scalars and
    are lifted onto the object; everything under the ``properties.`` prefix is
    a user property and stays in the dict.
    """
    paths = _read(bundle_dir, "eav.paths") or {"path_index": [], "path": []}
    path_name = dict(zip(paths["path_index"], paths["path"]))

    eav = _read(bundle_dir, "eav.eav")
    if not eav:
        return

    for i, obj_k in enumerate(eav["object_index"]):
        obj = by_k.get(obj_k)
        if obj is None:
            continue
        path = path_name.get(eav["path_index"][i])
        if path is None:
            continue
        value = _eav_value(eav, i)
        if path == "name":
            obj.name = value
        elif path == "speckle_type":
            obj.speckle_type = value
        else:
            obj.properties[path] = value
