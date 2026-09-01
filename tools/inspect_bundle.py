"""Reads a Speckle parquet bundle back into a readable, assertable summary.

The bundle written by ``BlenderBundleExporter`` is 13 parquet tables of interned
indices — correct but unreadable. This module joins them back into names and
values so a publish can be checked without a server or the viewer:

    python tools/inspect_bundle.py /tmp/speckle-bundle

Runs both in the repo venv and inside Blender (pyarrow ships with the
connector's dependency set), so ``headless_export.py`` can self-check.
"""

from __future__ import annotations

import glob
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BundleSummary:
    """Decoded bundle contents, in host-app terms rather than bundle indices."""

    schema_version: Optional[int] = None
    objects: int = 0
    object_ids: List[str] = field(default_factory=list)
    geometries: int = 0
    geometry_types: Dict[str, int] = field(default_factory=dict)
    collections: List[str] = field(default_factory=list)
    # collection name -> parent collection name (None at the root)
    collection_parents: Dict[str, Optional[str]] = field(default_factory=dict)
    # object application_id -> the collection it was placed in
    object_collections: Dict[str, str] = field(default_factory=dict)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    # instancing: DEFINITION node names, and one entry per INSTANCE placement
    definitions: List[str] = field(default_factory=list)
    instances: int = 0
    # placement object application_id -> the definition it places
    instance_definitions: Dict[str, Optional[str]] = field(default_factory=dict)
    # placement object application_id -> its transform's translation [x, y, z]
    instance_translations: Dict[str, List[float]] = field(default_factory=dict)
    # definition name -> how many members it owns (distinct DEFINES* ordinals)
    definition_members: Dict[str, int] = field(default_factory=dict)
    # parent object application_id -> its SUBELEMENT children, in ordinal order
    subelements: Dict[str, List[str]] = field(default_factory=dict)
    relations: Dict[str, int] = field(default_factory=dict)
    scene_views: List[str] = field(default_factory=list)
    # application_id -> {eav path: value}
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def material_names(self) -> List[str]:
        return [m["name"] for m in self.materials]

    @property
    def eav_paths(self) -> List[str]:
        seen: List[str] = []
        for props in self.properties.values():
            for path in props:
                if path not in seen:
                    seen.append(path)
        return seen


def _read(bundle_dir: str, suffix: str) -> Optional[Dict[str, List[Any]]]:
    """Read one bundle table as columns. Returns None when the table is absent.

    Tables are named ``<version_id>.<table>.parquet``, and the version id is
    only known at publish time, so match on the suffix instead.
    """
    import pyarrow.parquet as pq

    matches = glob.glob(os.path.join(bundle_dir, f"*.{suffix}.parquet"))
    if not matches:
        return None
    return pq.read_table(matches[0]).to_pydict()


def _eav_value(row: Dict[str, List[Any]], i: int) -> Any:
    """Pick the populated value column for one eav row.

    Numbers land in both ``value_string`` and ``value_double``; the double is
    the truer reading, so it wins.
    """
    if row["value_double"][i] is not None:
        return row["value_double"][i]
    if row["value_boolean"][i] is not None:
        return row["value_boolean"][i]
    return row["value_string"][i]


def _translation(transform: Optional[str]) -> List[float]:
    """Pull [x, y, z] out of a row-major 4x4 stored as a CSV string."""
    if not transform:
        return []
    values = [float(v) for v in transform.split(",")]
    if len(values) != 16:
        return []
    return [round(values[3], 4), round(values[7], 4), round(values[11], 4)]


def summarize(bundle_dir: str) -> BundleSummary:
    """Decode a bundle directory into a BundleSummary."""
    s = BundleSummary()

    meta = _read(bundle_dir, "envelope.meta")
    if meta and meta["schema_version"]:
        s.schema_version = meta["schema_version"][0]

    objects = _read(bundle_dir, "eav.objects") or {"application_id": []}
    s.object_ids = list(objects["application_id"])
    s.objects = len(s.object_ids)

    geometries = _read(bundle_dir, "geometries") or {"type": []}
    s.geometries = len(geometries["type"])
    s.geometry_types = dict(Counter(geometries["type"]))

    # nodes hold collections and materials, discriminated by `kind`
    kinds = _read(bundle_dir, "envelope.node_kinds") or {"kind": [], "name": []}
    kind_name = dict(zip(kinds["kind"], kinds["name"]))
    nodes = _read(bundle_dir, "envelope.nodes")
    container_names: Dict[int, str] = {}
    definition_names: Dict[int, str] = {}
    instance_nodes: Dict[int, Dict[str, Any]] = {}
    if nodes:
        for i, kind in enumerate(nodes["kind"]):
            name = kind_name.get(kind)
            if name == "CONTAINER":
                s.collections.append(nodes["name"][i])
                container_names[nodes["id"][i]] = nodes["name"][i]
            elif name == "DEFINITION":
                s.definitions.append(nodes["name"][i])
                definition_names[nodes["id"][i]] = nodes["name"][i]
            elif name == "INSTANCE":
                instance_nodes[nodes["id"][i]] = {
                    "def_ref": nodes["def_ref"][i],
                    "transform": nodes["transform"][i],
                }
            elif name == "MATERIAL":
                s.materials.append(
                    {
                        "name": nodes["name"][i],
                        "argb": nodes["argb"][i],
                        "opacity": nodes["opacity"][i],
                        "metalness": nodes["metalness"][i],
                        "roughness": nodes["roughness"][i],
                    }
                )

    # collection parentage is a node field, not a relation: a CONTAINER's
    # def_ref points at its parent CONTAINER
    if nodes:
        for i, node_id in enumerate(nodes["id"]):
            if node_id not in container_names:
                continue
            parent = nodes["def_ref"][i]
            s.collection_parents[container_names[node_id]] = (
                container_names.get(parent) if parent is not None else None
            )

    rel_types = _read(bundle_dir, "envelope.rel_types") or {"rel": [], "name": []}
    rel_name = dict(zip(rel_types["rel"], rel_types["name"]))
    relations = _read(bundle_dir, "envelope.relations")
    if relations:
        s.relations = dict(
            Counter(rel_name.get(r, f"rel:{r}") for r in relations["rel"])
        )
        # IN_COLLECTION: src is an object index, dst a container node id.
        # Decoding it is the difference between "3 objects were placed" and
        # "3 objects were placed in the right collections".
        s.instances = len(instance_nodes)
        # a definition's member count is its distinct DEFINES* ordinals: all the
        # geometry of one member shares that member's ordinal
        member_ords: Dict[str, set] = {}
        # SUBELEMENT is object -> object, so both ends index object_ids
        subelement_ords: Dict[str, List[tuple]] = {}
        for i, rel in enumerate(relations["rel"]):
            name = rel_name.get(rel)
            src, dst = relations["src"][i], relations["dst"][i]

            if name == "SUBELEMENT":
                if src < len(s.object_ids) and dst < len(s.object_ids):
                    subelement_ords.setdefault(s.object_ids[src], []).append(
                        (relations["ord"][i], s.object_ids[dst])
                    )

            elif name == "IN_COLLECTION":
                if src < len(s.object_ids) and dst in container_names:
                    s.object_collections[s.object_ids[src]] = container_names[dst]

            elif name == "DISPLAY_INSTANCE":
                # object -> INSTANCE node -> (def_ref) -> DEFINITION node
                if src < len(s.object_ids) and dst in instance_nodes:
                    node = instance_nodes[dst]
                    app_id = s.object_ids[src]
                    s.instance_definitions[app_id] = definition_names.get(
                        node["def_ref"]
                    )
                    s.instance_translations[app_id] = _translation(node["transform"])

            elif name in ("DEFINES", "DEFINES_INSTANCE"):
                definition = definition_names.get(src)
                if definition is not None:
                    member_ords.setdefault(definition, set()).add(relations["ord"][i])

        s.definition_members = {name: len(ords) for name, ords in member_ords.items()}
        s.subelements = {
            parent: [child for _, child in sorted(pairs)]
            for parent, pairs in subelement_ords.items()
        }

    views = _read(bundle_dir, "envelope.scene_views")
    if views:
        s.scene_views = list(views["name"])

    # properties: join eav rows onto path names and object application ids
    paths = _read(bundle_dir, "eav.paths") or {"path_index": [], "path": []}
    path_name = dict(zip(paths["path_index"], paths["path"]))
    eav = _read(bundle_dir, "eav.eav")
    if eav:
        for i in range(len(eav["object_index"])):
            obj_i = eav["object_index"][i]
            if obj_i >= len(s.object_ids):
                continue
            app_id = s.object_ids[obj_i]
            path = path_name.get(eav["path_index"][i], f"?{eav['path_index'][i]}")
            s.properties.setdefault(app_id, {})[path] = _eav_value(eav, i)

    return s


def format_report(s: BundleSummary) -> str:
    """Render a summary as a diffable text block."""
    lines = [
        f"schema_version : {s.schema_version}",
        f"objects        : {s.objects}",
        f"geometries     : {s.geometries}  {s.geometry_types}",
        f"collections    : {s.collections}",
        f"coll_parents   : {s.collection_parents}",
        f"placement      : {s.object_collections}",
        f"scene_views    : {s.scene_views}",
        f"relations      : {s.relations}",
        f"materials      : {len(s.materials)}",
    ]
    if s.definitions or s.instances:
        lines += [
            f"definitions    : {s.definitions}  members={s.definition_members}",
            f"instances      : {s.instances}  {s.instance_definitions}",
            f"placements     : {s.instance_translations}",
        ]
    if s.subelements:
        lines.append(f"subelements    : {s.subelements}")
    for m in s.materials:
        lines.append(
            f"  - {m['name']!r} argb={m['argb']} opacity={m['opacity']} "
            f"metalness={m['metalness']} roughness={m['roughness']}"
        )
    lines.append("properties     :")
    for app_id, props in s.properties.items():
        lines.append(f"  {app_id}")
        for path, value in props.items():
            lines.append(f"    {path} = {value!r}")
    return "\n".join(lines)


def check(s: BundleSummary, expect: Dict[str, Any]) -> List[str]:
    """Compare a summary against a fixture's EXPECT block.

    Counts and name sets are exact; ``properties`` and ``eav_paths`` are subset
    checks, so a fixture pins the paths it cares about without breaking every
    time an unrelated property is added. Returns human-readable failures.
    """
    failures: List[str] = []

    def eq(label: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            failures.append(f"{label}: expected {wanted!r}, got {actual!r}")

    for key, wanted in expect.items():
        if key == "objects":
            eq("objects", s.objects, wanted)
        elif key == "geometries":
            eq("geometries", s.geometries, wanted)
        elif key == "geometry_types":
            eq("geometry_types", s.geometry_types, dict(wanted))
        elif key == "collections":
            eq("collections", sorted(s.collections), sorted(wanted))
        elif key == "collection_parents":
            eq("collection_parents", s.collection_parents, dict(wanted))
        elif key == "object_collections":
            # keyed by object name; bundle ids are prefixed ("Object:Cube")
            actual = {
                app_id.split(":", 1)[-1]: coll
                for app_id, coll in s.object_collections.items()
            }
            eq("object_collections", actual, dict(wanted))
        elif key == "subelements":
            # keyed by object name at both ends, like object_collections
            actual = {
                parent.split(":", 1)[-1]: [c.split(":", 1)[-1] for c in children]
                for parent, children in s.subelements.items()
            }
            eq("subelements", actual, {k: list(v) for k, v in dict(wanted).items()})
        elif key == "definitions":
            eq("definitions", sorted(s.definitions), sorted(wanted))
        elif key == "instances":
            eq("instances", s.instances, wanted)
        elif key == "definition_members":
            eq("definition_members", s.definition_members, dict(wanted))
        elif key == "instance_definitions":
            actual = {
                app_id.split(":", 1)[-1]: definition
                for app_id, definition in s.instance_definitions.items()
            }
            eq("instance_definitions", actual, dict(wanted))
        elif key == "instance_translations":
            actual = {
                app_id.split(":", 1)[-1]: [round(v, 3) for v in xyz]
                for app_id, xyz in s.instance_translations.items()
            }
            eq(
                "instance_translations",
                actual,
                {
                    k: [round(float(v), 3) for v in xyz]
                    for k, xyz in dict(wanted).items()
                },
            )
        elif key == "materials":
            eq("materials", len(s.materials), wanted)
        elif key == "material_names":
            eq("material_names", sorted(s.material_names), sorted(wanted))
        elif key == "relations":
            for rel, count in dict(wanted).items():
                eq(f"relations[{rel}]", s.relations.get(rel, 0), count)
        elif key == "scene_views":
            eq("scene_views", s.scene_views, list(wanted))
        elif key == "eav_paths":
            missing = [p for p in wanted if p not in s.eav_paths]
            if missing:
                failures.append(f"eav_paths: missing {missing} (have {s.eav_paths})")
        elif key == "properties":
            for app_id, wanted_props in dict(wanted).items():
                match = next(
                    (v for k, v in s.properties.items() if k.endswith(app_id)), None
                )
                if match is None:
                    failures.append(
                        f"properties: no object matching {app_id!r} "
                        f"(have {list(s.properties)})"
                    )
                    continue
                for path, value in wanted_props.items():
                    if path not in match:
                        failures.append(
                            f"properties[{app_id}]: missing path {path!r} "
                            f"(have {list(match)})"
                        )
                    elif match[path] != value:
                        failures.append(
                            f"properties[{app_id}][{path}]: expected {value!r}, "
                            f"got {match[path]!r}"
                        )
        else:
            failures.append(f"unknown EXPECT key {key!r}")

    return failures


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", help="directory holding the *.parquet bundle")
    args = parser.parse_args()

    if not glob.glob(os.path.join(args.bundle_dir, "*.parquet")):
        print(f"No parquet files in {args.bundle_dir}")
        return 1
    print(format_report(summarize(args.bundle_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
