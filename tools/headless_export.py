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
import importlib.util
import os
import sys
import tempfile
from typing import Any, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_DIR = os.path.join(REPO_ROOT, "tools", "fixtures")


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
        return list(fixture.build()), fixture

    bpy.ops.wm.open_mainfile(filepath=os.path.expanduser(args.blend))
    if args.objects:
        wanted = [n.strip() for n in args.objects.split(",")]
        missing = [n for n in wanted if n not in bpy.data.objects]
        if missing:
            raise SystemExit(f"Objects not in {args.blend}: {missing}")
        return [bpy.data.objects[n] for n in wanted], None
    return list(bpy.context.scene.objects), None


def export(objects: List[Any], out_dir: str, apply_modifiers: bool) -> Tuple[str, int]:
    """Run conversion + bundle export. Returns (root_id, object_count)."""
    import bpy

    from bpy_speckle.connector.operations.publish_operation import (
        build_collection_hierarchy,
    )
    from bpy_speckle.converter.to_speckle.bundle_exporter import BlenderBundleExporter
    from bpy_speckle.converter.to_speckle.material_to_speckle import (
        add_render_material_proxies_to_base,
    )

    root = build_collection_hierarchy(bpy.context, objects, apply_modifiers)
    if root is None:
        raise SystemExit("build_collection_hierarchy returned None — nothing converted")
    add_render_material_proxies_to_base(root, objects)

    exporter = BlenderBundleExporter(out_dir, "headless")
    root_id, count = exporter.export(root)
    for geo_id, error in exporter.conversion_errors:
        print(f"  ! skipped geometry {geo_id!r}: {error}")
    return root_id, count


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

    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import inspect_bundle

    summary = inspect_bundle.summarize(out_dir)
    print(inspect_bundle.format_report(summary))

    expect = getattr(fixture, "EXPECT", None) if fixture else None
    if not expect:
        print(f"\n(no EXPECT block — report only)  re-inspect: {out_dir}")
        return 0

    failures = inspect_bundle.check(summary, expect)
    if failures:
        print(f"\nFAIL {label}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nPASS {label} ({len(expect)} expectation groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
