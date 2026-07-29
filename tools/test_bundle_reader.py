"""Exercises ``bundle_reader`` against synthetic cross-connector bundles.

The publish harness can only produce Blender-shaped bundles — one authored
collection tree, nothing else. Cross-connector regressions live exactly in the
shapes Blender never writes: multiple parentless CONTAINER axes, membership
relations other than IN_COLLECTION, adversarial node row order. So this builds
those bundles by hand with pyarrow and asserts on what the reader joins back.

    uv run python tools/test_bundle_reader.py

Needs no Blender: ``bundle_reader`` is deliberately free of ``bpy``, which is
what makes this runnable in the repo venv. The bake side (``bundle_to_native``)
still needs real Blender and stays with the fixture harness.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from typing import Any, Dict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# import by path: importing the bpy_speckle package would pull in bpy
_spec = importlib.util.spec_from_file_location(
    "bundle_reader",
    os.path.join(REPO_ROOT, "bpy_speckle/converter/from_bundle/bundle_reader.py"),
)
bundle_reader = importlib.util.module_from_spec(_spec)
# dataclasses resolves the module's postponed annotations through sys.modules,
# so the module must be registered before it executes
sys.modules["bundle_reader"] = bundle_reader
_spec.loader.exec_module(bundle_reader)

# rel/kind ids as catalogued in the bundle spec's rel_types / node_kinds
DEFINITION, INSTANCE, CONTAINER = 1, 2, 7
SUBELEMENT, DEFINES, DISPLAY_INSTANCE = 3, 4, 8
IN_COLLECTION, IN_MODEL, IN_SYSTEM, IN_GROUP = 10, 11, 14, 17
REL_NAMES = {
    SUBELEMENT: "SUBELEMENT",
    DEFINES: "DEFINES",
    DISPLAY_INSTANCE: "DISPLAY_INSTANCE",
    IN_COLLECTION: "IN_COLLECTION",
    IN_MODEL: "IN_MODEL",
    IN_SYSTEM: "IN_SYSTEM",
    IN_GROUP: "IN_GROUP",
}

IDENTITY = "1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"


def _write(bundle_dir: str, table: str, columns: Dict[str, list]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table(columns), os.path.join(bundle_dir, f"v0.{table}.parquet"))


def write_bundle(
    bundle_dir: str,
    containers: list,  # (id, name, def_ref, subtype)
    objects: list,  # application_id, k is the list index
    relations: list,  # (rel, src, dst) or (rel, src, dst, ord)
    with_subtype_column: bool = True,
    properties: list = None,  # (object k, eav path, scalar value)
    definitions: list = None,  # (node id, name)
    instances: list = None,  # (node id, def_ref, transform csv, units)
    geometries: list = None,  # (geometry k, sgeo type, content bytes)
) -> None:
    """Write the minimal table set the reader joins.

    Shared with ``test_bundle_bake.py``, which bakes these same shapes inside
    headless Blender.
    """
    definitions = definitions or []
    instances = instances or []
    nodes: Dict[str, list] = {
        "id": [c[0] for c in containers]
        + [d[0] for d in definitions]
        + [i[0] for i in instances],
        "kind": [CONTAINER] * len(containers)
        + [DEFINITION] * len(definitions)
        + [INSTANCE] * len(instances),
        "name": [c[1] for c in containers]
        + [d[1] for d in definitions]
        + [None] * len(instances),
        "def_ref": [c[2] for c in containers]
        + [None] * len(definitions)
        + [i[1] for i in instances],
    }
    if instances:
        # the reader only touches these columns on INSTANCE rows, and the real
        # writer only emits them when instances exist
        pad = [None] * (len(containers) + len(definitions))
        nodes["transform"] = pad + [i[2] for i in instances]
        nodes["units"] = pad + [i[3] for i in instances]
    if with_subtype_column:
        nodes["subtype"] = [c[3] for c in containers] + [None] * (
            len(definitions) + len(instances)
        )
    _write(
        bundle_dir,
        "envelope.node_kinds",
        {
            "kind": [DEFINITION, INSTANCE, CONTAINER],
            "name": ["DEFINITION", "INSTANCE", "CONTAINER"],
        },
    )
    _write(bundle_dir, "envelope.nodes", nodes)
    _write(
        bundle_dir,
        "eav.objects",
        {"object_index": list(range(len(objects))), "application_id": objects},
    )
    _write(
        bundle_dir,
        "envelope.rel_types",
        {"rel": list(REL_NAMES), "name": list(REL_NAMES.values())},
    )
    _write(
        bundle_dir,
        "envelope.relations",
        {
            "rel": [r[0] for r in relations],
            "src": [r[1] for r in relations],
            "dst": [r[2] for r in relations],
            "ord": [r[3] if len(r) > 3 else None for r in relations],
        },
    )
    if geometries:
        _write(
            bundle_dir,
            "geometries",
            {
                "geometryIndex": [g[0] for g in geometries],
                "content": [g[2] for g in geometries],
                "type": [g[1] for g in geometries],
            },
        )
    if properties:
        # numbers land in value_double, matching the real writer — an int
        # published as 42 deliberately reads back as 42.0
        paths = sorted({p for _, p, _ in properties})
        path_index = {p: i for i, p in enumerate(paths)}
        _write(
            bundle_dir,
            "eav.paths",
            {"path_index": list(path_index.values()), "path": paths},
        )
        values = [v for _, _, v in properties]
        _write(
            bundle_dir,
            "eav.eav",
            {
                "object_index": [k for k, _, _ in properties],
                "path_index": [path_index[p] for _, p, _ in properties],
                "value_string": [v if isinstance(v, str) else None for v in values],
                "value_double": [
                    float(v)
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                    else None
                    for v in values
                ],
                "value_boolean": [v if isinstance(v, bool) else None for v in values],
            },
        )


def build_bundle(bundle_dir: str, **kwargs: Any) -> Any:
    """Write a synthetic bundle and join it back through the reader."""
    write_bundle(bundle_dir, **kwargs)
    return bundle_reader.read_bundle(bundle_dir)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def navis_federation() -> None:
    """Two models and a network, all parentless — no authored collections.

    The network is deliberately the first node row: under first-parentless-row
    root selection it would have been crowned the model root.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[
                (1, "Supply Air", None, "Network"),
                (2, "hvac.nwc", None, "Model"),
                (3, "arch.nwc", None, "Model"),
            ],
            objects=["duct-1", "wall-1"],
            relations=[
                (IN_SYSTEM, 0, 1),
                (IN_MODEL, 0, 2),
                (IN_MODEL, 1, 3),
            ],
        )
    check(bundle.root_collection_id is None, "a Network must never become the root")
    check(
        [c.subtype for c in bundle.containers.values()]
        == ["Network", "Model", "Model"],
        "subtype must survive the read",
    )
    check(
        not any(c.is_collection for c in bundle.containers.values()),
        "no container here belongs to the authored tree",
    )
    duct, wall = bundle.objects
    check(duct.model_id == 2 and wall.model_id == 3, "IN_MODEL must resolve")
    check(duct.system_ids == [1], "IN_SYSTEM must resolve")
    check(duct.collection_id is None, "no IN_COLLECTION edge was written")


def revit_systems_overlap() -> None:
    """An MEP object belongs to every system that runs through it."""
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[
                (1, "Supply", None, "MEP System"),
                (2, "Return", None, "MEP System"),
            ],
            objects=["ahu-1"],
            relations=[(IN_SYSTEM, 0, 1), (IN_SYSTEM, 0, 2)],
        )
    check(bundle.root_collection_id is None, "systems alone give no root")
    check(bundle.objects[0].system_ids == [1, 2], "memberships must accumulate")


def rhino_groups_beside_layers() -> None:
    """Groups are a second axis: the object keeps its layer AND its groups.

    The group rows come before the collection rows, so root selection must go
    by subtype, not row order. GroupB nests inside GroupA via def_ref.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[
                (2, "GroupA", None, "Group"),
                (3, "GroupB", 2, "Group"),
                (5, "Root", None, "Collection"),
                (6, "Layer1", 5, "Collection"),
            ],
            objects=["curve-1"],
            relations=[
                (IN_COLLECTION, 0, 6),
                (IN_GROUP, 0, 2),
                (IN_GROUP, 0, 3),
            ],
        )
    check(bundle.root_collection_id == 5, "the Collection root must win over row order")
    obj = bundle.objects[0]
    check(obj.collection_id == 6, "IN_COLLECTION must still resolve")
    check(obj.group_ids == [2, 3], "overlapping groups must accumulate")
    check(
        [c.node_id for c in bundle.child_containers(5)] == [6],
        "collection nesting must survive",
    )


def legacy_bundle_without_subtype() -> None:
    """Pre-polymorphism bundles have no subtype column; every container was an
    authored collection, and root choice must still be deterministic."""
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[
                (9, "WrittenFirst", None, None),
                (4, "LowerNodeId", None, None),
            ],
            objects=[],
            relations=[],
            with_subtype_column=False,
        )
    check(
        all(c.is_collection for c in bundle.containers.values()),
        "subtype-less containers are authored collections",
    )
    check(
        bundle.root_collection_id == 4,
        "ties must break on node id, not on row order",
    )


def multiple_collection_roots() -> None:
    """Two parentless authored collections: the lower node id is the root."""
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[
                (8, "SecondRoot", None, "Collection"),
                (3, "FirstRoot", None, "Collection"),
                (1, "A System", None, "MEP System"),
            ],
            objects=[],
            relations=[],
        )
    check(bundle.root_collection_id == 3, "lowest Collection node id wins")


def revit_family_instance_atomized() -> None:
    """One object, several DISPLAY_INSTANCE edges — every placement survives.

    Revit atomizes a family instance into one DEFINITION/INSTANCE pair per
    material, so a chair arrives as a cushions placement plus a frame
    placement on the same object. A scalar reading kept only the last row and
    silently dropped the rest of the element's geometry (the
    chairs-without-cushions regression). The edges are written frame-first
    here so that ord, not row order, must decide the sequence.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        bundle = build_bundle(
            bundle_dir,
            containers=[],
            objects=["chair-1"],
            definitions=[(1, "chair-cushions"), (3, "chair-frame")],
            instances=[(2, 1, IDENTITY, "m"), (4, 3, IDENTITY, "m")],
            geometries=[(0, "mesh", b"\x00"), (1, "mesh", b"\x00")],
            relations=[
                (DEFINES, 1, 0, 0),
                (DEFINES, 3, 1, 0),
                (DISPLAY_INSTANCE, 0, 4, 1),
                (DISPLAY_INSTANCE, 0, 2, 0),
            ],
        )
    chair = bundle.objects[0]
    check(chair.is_placement, "an object with placements is a placement")
    check(
        chair.instance_ids == [2, 4],
        f"every placement must survive in ord order, got {chair.instance_ids}",
    )
    check(
        bundle.instances[2].def_ref == 1 and bundle.instances[4].def_ref == 3,
        "each instance keeps its own definition",
    )
    check(
        bundle.definitions[1].members == {0: [0]}
        and bundle.definitions[3].members == {0: [1]},
        "DEFINES resolves definition node ids against geometry Ks",
    )


SCENARIOS = [
    navis_federation,
    revit_systems_overlap,
    rhino_groups_beside_layers,
    legacy_bundle_without_subtype,
    multiple_collection_roots,
    revit_family_instance_atomized,
]


def main() -> int:
    failed = 0
    for scenario in SCENARIOS:
        try:
            scenario()
        except AssertionError as e:
            print(f"FAIL  {scenario.__name__}: {e}")
            failed += 1
        else:
            print(f"ok    {scenario.__name__}")
    if failed:
        print(f"\n{failed} of {len(SCENARIOS)} scenarios failed")
        return 1
    print(f"\nAll {len(SCENARIOS)} scenarios passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
