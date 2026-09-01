"""Exercises specklepy's bundle reader against synthetic cross-connector bundles.

The publish harness can only produce Blender-shaped bundles — one authored
collection tree, nothing else. Cross-connector regressions live exactly in the
shapes Blender never writes: multiple parentless CONTAINER axes, membership
relations other than IN_COLLECTION, adversarial node row order (the
ENG-9025/9026/9027 family). So this builds those bundles by hand with pyarrow
and asserts on what ``specklepy.bundle.read_bundle`` + the ``Model`` facade —
the exact surface the connector's bake consumes — join back.

    uv run python tools/test_bundle_reader.py

Needs no Blender, so it runs in the repo venv. The bake side
(``bundle_to_native``) consumes the same ``Model`` in ``test_bundle_bake.py``
inside headless Blender, which also covers root-collection selection — a
bake-side decision the reader deliberately does not make.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, Dict

from specklepy.bundle.bundle_reader import read_bundle
from specklepy.bundle.model import Model
from specklepy.bundle.spec import NodeKind, Rel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# rel/kind ids straight from the vendored spec, so a spec bump fails loudly
# here instead of silently writing tables the reader maps differently
DEFINITION, INSTANCE, MATERIAL, CONTAINER = (
    int(NodeKind.DEFINITION),
    int(NodeKind.INSTANCE),
    int(NodeKind.MATERIAL),
    int(NodeKind.CONTAINER),
)
DISPLAY = int(Rel.DISPLAY)
SUBELEMENT = int(Rel.SUBELEMENT)
DEFINES = int(Rel.DEFINES)
HAS_MATERIAL = int(Rel.HAS_MATERIAL)
DISPLAY_INSTANCE = int(Rel.DISPLAY_INSTANCE)
IN_COLLECTION = int(Rel.IN_COLLECTION)
IN_MODEL = int(Rel.IN_MODEL)
IN_SYSTEM = int(Rel.IN_SYSTEM)
IN_GROUP = int(Rel.IN_GROUP)
REL_NAMES = {
    DISPLAY: "DISPLAY",
    SUBELEMENT: "SUBELEMENT",
    DEFINES: "DEFINES",
    HAS_MATERIAL: "HAS_MATERIAL",
    DISPLAY_INSTANCE: "DISPLAY_INSTANCE",
    IN_COLLECTION: "IN_COLLECTION",
    IN_MODEL: "IN_MODEL",
    IN_SYSTEM: "IN_SYSTEM",
    IN_GROUP: "IN_GROUP",
}

IDENTITY = "1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"

# every column specklepy's node reader touches; synthetic rows pad the unused
# ones with None
_NODE_EXTRA_COLUMNS = (
    "transform",
    "units",
    "subtype",
    "argb",
    "opacity",
    "metalness",
    "roughness",
    "emissive",
    "ior",
    "elevation",
    "gh_topology",
)


def _write(bundle_dir: str, table: str, columns: Dict[str, list]) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table(columns), os.path.join(bundle_dir, f"v0.{table}.parquet"))


def write_bundle(
    bundle_dir: str,
    containers: list,  # (id, name, def_ref, subtype)
    objects: list,  # application_id, k is the list index
    relations: list,  # (rel, src, dst) or (rel, src, dst, ord)
    properties: list = None,  # (object k, eav path, scalar value)
    definitions: list = None,  # (node id, name)
    instances: list = None,  # (node id, def_ref, transform csv, units)
    geometries: list = None,  # (geometry k, sgeo type, content bytes)
    materials: list = None,  # (node id, name, argb, opacity, metalness, roughness)
) -> None:
    """Write the minimal table set specklepy's reader joins.

    Shared with ``test_bundle_bake.py``, which bakes these same shapes inside
    headless Blender.
    """
    definitions = definitions or []
    instances = instances or []
    materials = materials or []
    row_count = len(containers) + len(definitions) + len(instances) + len(materials)
    nodes: Dict[str, list] = {
        "id": [c[0] for c in containers]
        + [d[0] for d in definitions]
        + [i[0] for i in instances]
        + [m[0] for m in materials],
        "kind": [CONTAINER] * len(containers)
        + [DEFINITION] * len(definitions)
        + [INSTANCE] * len(instances)
        + [MATERIAL] * len(materials),
        "name": [c[1] for c in containers]
        + [d[1] for d in definitions]
        + [None] * len(instances)
        + [m[1] for m in materials],
        "def_ref": [c[2] for c in containers]
        + [None] * len(definitions)
        + [i[1] for i in instances]
        + [None] * len(materials),
    }
    for column in _NODE_EXTRA_COLUMNS:
        nodes[column] = [None] * row_count
    nodes["subtype"] = [c[3] for c in containers] + [None] * (
        len(definitions) + len(instances) + len(materials)
    )
    if instances:
        pad = [None] * (len(containers) + len(definitions))
        material_pad = [None] * len(materials)
        nodes["transform"] = pad + [i[2] for i in instances] + material_pad
        nodes["units"] = pad + [i[3] for i in instances] + material_pad
    if materials:
        pad = [None] * (len(containers) + len(definitions) + len(instances))
        nodes["argb"] = pad + [m[2] for m in materials]
        nodes["opacity"] = pad + [m[3] for m in materials]
        nodes["metalness"] = pad + [m[4] for m in materials]
        nodes["roughness"] = pad + [m[5] for m in materials]
    _write(
        bundle_dir,
        "envelope.node_kinds",
        {
            "kind": [DEFINITION, INSTANCE, MATERIAL, CONTAINER],
            "name": ["DEFINITION", "INSTANCE", "MATERIAL", "CONTAINER"],
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
    # eav.paths and eav.eav are required tables, so they are always written —
    # empty when the scenario carries no properties
    properties = properties or []
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


def read_model(bundle_dir: str) -> Model:
    """Wrap a written bundle directory in the SDK's ``Model`` facade."""
    files = sorted(os.path.join(bundle_dir, f) for f in sorted(os.listdir(bundle_dir)))
    return Model(
        "project", "model", "version", bundle_dir, files, read_bundle(bundle_dir)
    )


def build_model(bundle_dir: str, **kwargs: Any) -> Model:
    """Write a synthetic bundle and join it back through the SDK reader."""
    write_bundle(bundle_dir, **kwargs)
    return read_model(bundle_dir)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _in_model_k(model: Model, obj) -> int | None:
    """The CONTAINER(Model) node k an object belongs to, via IN_MODEL."""
    return model.bundle.relations.object_node_by_rel.get(int(Rel.IN_MODEL), {}).get(
        obj.k
    )


def navis_federation() -> None:
    """Two models and a network, all parentless — no authored collections.

    The network is deliberately the first node row: root selection (bake-side,
    covered in ``test_bundle_bake.py``) must never crown it, and the reader
    must keep every axis's subtype and membership intact for that decision.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        model = build_model(
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
        check(
            [c.subtype for c in model.collections] == ["Network", "Model", "Model"],
            "subtype must survive the read",
        )
        check(
            not any(c.subtype == "Collection" for c in model.collections),
            "no container here belongs to the authored tree",
        )
        duct = model.object_by_application_id("duct-1")
        wall = model.object_by_application_id("wall-1")
        check(
            _in_model_k(model, duct) == 2 and _in_model_k(model, wall) == 3,
            "IN_MODEL must resolve",
        )
        check(
            duct.system is not None and duct.system.k == 1,
            "IN_SYSTEM must resolve",
        )
        check(duct.collection is None, "no IN_COLLECTION edge was written")


def revit_systems_overlap() -> None:
    """An MEP object belongs to every system that runs through it.

    Known SDK narrowing: specklepy reads IN_SYSTEM as single-valued (the last
    edge wins), so only one membership survives today. This pins that the edge
    resolves at all; restoring the overlap is a specklepy change, not a
    connector shim.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        model = build_model(
            bundle_dir,
            containers=[
                (1, "Supply", None, "MEP System"),
                (2, "Return", None, "MEP System"),
            ],
            objects=["ahu-1"],
            relations=[(IN_SYSTEM, 0, 1), (IN_SYSTEM, 0, 2)],
        )
        ahu = model.object_by_application_id("ahu-1")
        check(ahu.system is not None, "an IN_SYSTEM membership must resolve")
        check(
            ahu.system.k == 2,
            "the SDK keeps the last IN_SYSTEM edge; if this fails because both "
            "now accumulate, delete this narrowing note and assert the overlap",
        )


def rhino_groups_beside_layers() -> None:
    """Groups are a second axis: the object keeps its layer AND its groups.

    The group rows come before the collection rows, so any consumer choosing a
    root must go by subtype, not row order. GroupB nests inside GroupA via
    def_ref.
    """
    with tempfile.TemporaryDirectory() as bundle_dir:
        model = build_model(
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
        curve = model.object_by_application_id("curve-1")
        check(
            curve.collection is not None and curve.collection.k == 6,
            "IN_COLLECTION must still resolve",
        )
        check(
            [g.k for g in curve.groups] == [2, 3],
            "overlapping groups must accumulate",
        )
        root = model.node(5)
        check(
            [c.k for c in root.children] == [6],
            "collection nesting must survive",
        )
        check(
            [g.k for g in model.node(2).children] == [3],
            "group nesting must survive",
        )


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
        model = build_model(
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
        chair = model.object_by_application_id("chair-1")
        placements = chair.placements
        check(
            [p.k for p in placements] == [2, 4],
            f"every placement must survive in ord order, got {[p.k for p in placements]}",
        )
        check(
            placements[0].definition.k == 1 and placements[1].definition.k == 3,
            "each instance keeps its own definition",
        )
        rels = model.bundle.relations
        check(
            rels.defines_by_definition == {1: [0], 3: [1]},
            "DEFINES resolves definition node ids against geometry Ks",
        )


SCENARIOS = [
    navis_federation,
    revit_systems_overlap,
    rhino_groups_beside_layers,
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
