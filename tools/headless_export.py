"""Runs the connector's publish conversion in headless Blender — no GUI, no server.

Publishing normally needs a running Blender, an account, and the viewer to check
the result. But conversion is separable: ``build_collection_hierarchy`` maps
Blender state to a Speckle ``Collection``, and ``BlenderBundleExporter`` writes
the parquet bundle to a plain directory. Only ``ArtifactPipeline`` needs the
network. This script drives everything up to that line, then decodes the bundle
back with ``inspect_bundle`` and checks it against the fixture's expectations.

    tools/run_fixture.sh cube_with_props           # fixture, with EXPECT checks
    tools/run_fixture.sh --blend ~/scenes/test.blend   # your own file

Exits nonzero when conversion fails or an expectation is unmet, so it works as
a test as well as an inspection tool.
"""

import argparse
import glob
import importlib.util
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_DIR = os.path.join(REPO_ROOT, "tools", "fixtures")

# EXPECT keys checked against the real receive reader rather than
# inspect_bundle's raw-parquet view; see check_receive.
RECEIVE_EXPECT_KEYS = ("receive_properties", "receive_root_fields")


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse the args Blender passes through after ``--``."""
    parser = argparse.ArgumentParser(prog="headless_export")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="fixture name under tools/fixtures/")
    source.add_argument("--blend", help="path to a .blend file to publish")
    parser.add_argument(
        "--objects",
        help="comma-separated object names (--blend only; default: whole scene)",
    )
    parser.add_argument("--out", help="bundle output dir (default: a temp dir)")
    parser.add_argument(
        "--no-modifiers",
        action="store_true",
        help="publish base meshes instead of modifier-evaluated ones",
    )
    return parser.parse_args(argv)


def load_fixture(name: str) -> Any:
    """Import a fixture module by name from tools/fixtures/."""
    path = name if name.endswith(".py") else os.path.join(FIXTURE_DIR, f"{name}.py")
    if not os.path.exists(path):
        available = sorted(
            f[:-3]
            for f in os.listdir(FIXTURE_DIR)
            if f.endswith(".py") and not f.startswith("_")
        )
        raise SystemExit(f"No fixture {name!r}. Available: {', '.join(available)}")

    spec = importlib.util.spec_from_file_location(f"speckle_fixture_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_scene(args: argparse.Namespace) -> Tuple[List[Any], Optional[Any]]:
    """Set up the Blender scene. Returns (objects to publish, fixture module)."""
    import bpy

    if args.fixture:
        fixture = load_fixture(args.fixture)
        # start from an empty scene so fixtures are reproducible in isolation
        bpy.ops.wm.read_factory_settings(use_empty=True)
        objects = list(fixture.build())
        # A fixture that sets `location` through the data API rather than an
        # operator leaves `matrix_world` stale until the depsgraph catches up.
        # Conversion reads it directly, so without this a fixture silently
        # publishes its geometry at the origin — and asserts that it did.
        bpy.context.view_layer.update()
        return objects, fixture

    bpy.ops.wm.open_mainfile(filepath=os.path.expanduser(args.blend))
    if args.objects:
        wanted = [n.strip() for n in args.objects.split(",")]
        missing = [n for n in wanted if n not in bpy.data.objects]
        if missing:
            raise SystemExit(f"Objects not in {args.blend}: {missing}")
        return [bpy.data.objects[n] for n in wanted], None

    # Only what the user could actually select. scene.objects also returns objects
    # in collections excluded from the view layer, which the publish selection can
    # never contain — and for an instanced "library" collection that is precisely
    # the set that must arrive as definition members, not as scene objects.
    visible = [obj for obj in bpy.context.scene.objects if obj.visible_get()]
    hidden = len(bpy.context.scene.objects) - len(visible)
    if hidden:
        print(f"  ({hidden} hidden/excluded object(s) not selectable — omitted)")
    return visible, None


def export(objects: List[Any], out_dir: str, apply_modifiers: bool) -> Tuple[str, int]:
    """Run conversion + bundle export. Returns (root_id, object_count)."""
    import bpy

    from bpy_speckle.connector.operations.publish_operation import (
        build_collection_hierarchy,
    )
    from bpy_speckle.converter.to_speckle.bundle_exporter import BlenderBundleExporter

    # build_collection_hierarchy attaches the material and instance proxies itself:
    # it expands the selection with collection-instance members, so it is the only
    # place that knows the full object list those proxies have to cover.
    root = build_collection_hierarchy(bpy.context, objects, apply_modifiers)
    if root is None:
        raise SystemExit("build_collection_hierarchy returned None — nothing converted")

    exporter = BlenderBundleExporter(out_dir, "headless")
    root_id, count = exporter.export(root)
    for geo_id, error in exporter.conversion_errors:
        print(f"  ! skipped geometry {geo_id!r}: {error}")
    return root_id, count


def inject_root_fields(out_dir: str, fields_by_name: Dict[str, Dict[str, Any]]) -> None:
    """Append bare root eav rows another producer could have written.

    Blender's own publish only puts ``name``/``type``/``speckle_type`` at the
    eav root, so covering the cross-producer case (a Rhino or Revit bundle with
    extra root scalars) means appending rows after the export: new paths into
    ``eav.paths``, new value rows into ``eav.eav``. Keyed by object name.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    def load(suffix: str) -> Tuple[str, Any]:
        (path,) = glob.glob(os.path.join(out_dir, f"*.{suffix}.parquet"))
        return path, pq.read_table(path)

    objects_path, objects_table = load("eav.objects")
    objects = objects_table.to_pydict()
    k_by_name = {
        app_id.split(":", 1)[-1]: k
        for k, app_id in zip(objects["object_index"], objects["application_id"])
    }

    paths_file, paths_table = load("eav.paths")
    eav_file, eav_table = load("eav.eav")
    paths, eav = paths_table.to_pydict(), eav_table.to_pydict()
    index_of = dict(zip(paths["path"], paths["path_index"]))

    for name, fields in fields_by_name.items():
        obj_k = k_by_name[name]  # a KeyError here is a fixture bug
        for path, value in fields.items():
            idx = index_of.get(path)
            if idx is None:
                idx = max(paths["path_index"], default=-1) + 1
                paths["path_index"].append(idx)
                paths["path"].append(path)
                index_of[path] = idx
            is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
            eav["object_index"].append(obj_k)
            eav["path_index"].append(idx)
            eav["value_string"].append(str(value))
            eav["value_double"].append(float(value) if is_number else None)
            eav["value_boolean"].append(value if isinstance(value, bool) else None)
            eav["unit"].append(None)
            eav["internal_definition_name"].append(None)

    pq.write_table(pa.table(paths, schema=paths_table.schema), paths_file)
    pq.write_table(pa.table(eav, schema=eav_table.schema), eav_file)


def check_receive(out_dir: str, expect: Dict[str, Any]) -> List[str]:
    """Check the receive-side EXPECT keys against the real bundle reader.

    inspect_bundle re-derives its view from the raw parquet; this stage instead
    asserts on what ``bundle_reader`` — the actual receive path — restores.
    ``receive_properties`` is the per-object dict a bake writes back as user
    custom properties (``properties.`` prefix stripped); ``receive_root_fields``
    is where the non-user root scalars must land instead. Both are compared
    exactly, not as subsets — the point is that nothing extra leaks.
    """
    from bpy_speckle.converter.from_bundle.bundle_reader import read_bundle

    bundle = read_bundle(out_dir)
    by_name = {o.application_id.split(":", 1)[-1]: o for o in bundle.objects}

    failures: List[str] = []
    for key in RECEIVE_EXPECT_KEYS:
        for name, wanted in dict(expect.get(key) or {}).items():
            obj = by_name.get(name)
            if obj is None:
                failures.append(f"{key}: no object {name!r} (have {sorted(by_name)})")
                continue
            if key == "receive_properties":
                actual = {
                    path[len("properties.") :]: value
                    for path, value in obj.properties.items()
                }
            else:
                actual = dict(obj.root_fields)
            if actual != dict(wanted):
                failures.append(
                    f"{key}[{name}]: expected {dict(wanted)!r}, got {actual!r}"
                )
    return failures


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parse_args(argv)

    # the repo root must precede the symlinked extension so `import bpy_speckle`
    # resolves to the working tree, not the installed add-on
    sys.path.insert(0, REPO_ROOT)

    objects, fixture = build_scene(args)
    if not objects:
        raise SystemExit("No objects to publish")

    label = args.fixture or os.path.basename(args.blend)
    out_dir = args.out or os.path.join(
        tempfile.gettempdir(), f"speckle-bundle-{label.replace('.blend', '')}"
    )
    os.makedirs(out_dir, exist_ok=True)
    for stale in os.listdir(out_dir):
        if stale.endswith(".parquet"):
            os.remove(os.path.join(out_dir, stale))

    print(f"\n=== {label}: {len(objects)} object(s) -> {out_dir}")
    root_id, count = export(objects, out_dir, not args.no_modifiers)
    print(f"=== exported root={root_id} objects={count}\n")

    # simulate a cross-producer bundle before anything reads it back
    inject = getattr(fixture, "INJECT_ROOT_FIELDS", None) if fixture else None
    if inject:
        inject_root_fields(out_dir, inject)
        print(f"  (injected cross-producer root fields: {inject})\n")

    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import inspect_bundle

    summary = inspect_bundle.summarize(out_dir)
    print(inspect_bundle.format_report(summary))

    expect = dict(getattr(fixture, "EXPECT", None) or {}) if fixture else {}
    # the receive_* keys are checked against the real bundle_reader rather than
    # inspect_bundle's raw-parquet view
    receive_expect = {k: expect.pop(k) for k in RECEIVE_EXPECT_KEYS if k in expect}
    expect_receive = getattr(fixture, "EXPECT_RECEIVE", None) if fixture else None

    if not expect and not receive_expect and not expect_receive:
        print(f"\n(no EXPECT block — report only)  re-inspect: {out_dir}")
        return 0

    failures = list(inspect_bundle.check(summary, expect)) if expect else []
    failures += check_receive(out_dir, receive_expect)

    # EXPECT_RECEIVE round-trips the bundle back through the receive bake, once
    # per instance loading mode — the same parquet the publish check just read.
    if expect_receive:
        import receive_probe

        for mode in sorted(expect_receive):
            facts = receive_probe.bake_and_probe(out_dir, mode)
            print(receive_probe.format_report(mode, facts))
            failures += [
                f"receive[{mode}]: {failure}"
                for failure in receive_probe.check(facts, expect_receive[mode])
            ]

    if failures:
        print(f"\nFAIL {label}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    groups = (
        len(expect)
        + len(receive_expect)
        + sum(len(v) for v in (expect_receive or {}).values())
    )
    print(f"\nPASS {label} ({groups} expectation groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
