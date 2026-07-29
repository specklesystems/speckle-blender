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
CONTAINER = 7
IN_COLLECTION, IN_MODEL, IN_SYSTEM, IN_GROUP = 10, 11, 14, 17
REL_NAMES = {
    IN_COLLECTION: "IN_COLLECTION",
    IN_MODEL: "IN_MODEL",
    IN_SYSTEM: "IN_SYSTEM",
    IN_GROUP: "IN_GROUP",
}


def _write(bundle_dir: str, table: str, columns: Dict[str, list]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table(columns), os.path.join(bundle_dir, f"v0.{table}.parquet"))


def write_bundle(
    bundle_dir: str,
    containers: list,  # (id, name, def_ref, subtype)
    objects: list,  # application_id, k is the list index
    relations: list,  # (rel, src object k, dst node id)
    with_subtype_column: bool = True,
) -> None:
    """Write the minimal table set the reader joins.

    Shared with ``test_bundle_bake.py``, which bakes these same shapes inside
    headless Blender.
    """
    nodes: Dict[str, list] = {
        "id": [c[0] for c in containers],
        "kind": [CONTAINER] * len(containers),
        "name": [c[1] for c in containers],
        "def_ref": [c[2] for c in containers],
    }
    if with_subtype_column:
        nodes["subtype"] = [c[3] for c in containers]
    _write(
        bundle_dir, "envelope.node_kinds", {"kind": [CONTAINER], "name": ["CONTAINER"]}
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
            "ord": [None] * len(relations),
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


SCENARIOS = [
    navis_federation,
    revit_systems_overlap,
    rhino_groups_beside_layers,
    legacy_bundle_without_subtype,
    multiple_collection_roots,
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
