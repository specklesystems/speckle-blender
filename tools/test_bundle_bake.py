"""Bakes synthetic cross-connector bundles in headless Blender and checks the
Outliner shape that comes out.

The publish fixtures can only make Blender-shaped bundles, so the container
axes Blender never writes — models, systems, groups — are fabricated with the
same table writer as ``test_bundle_reader.py`` and pushed through the real
receive path (``read_bundle`` -> ``bake_bundle``):

    /Applications/Blender.app/Contents/MacOS/Blender --background \\
        --factory-startup -noaudio --python tools/test_bundle_bake.py

Objects here carry no geometry on purpose: a geometry-less object bakes to a
real (shapeless) Blender object, which is all placement assertions need.
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the repo root must precede the symlinked extension so `import bpy_speckle`
# resolves to the working tree, not the installed add-on
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import bpy  # noqa: E402

from test_bundle_reader import (  # noqa: E402
    DISPLAY_INSTANCE,
    IN_COLLECTION,
    IN_GROUP,
    IN_MODEL,
    IN_SYSTEM,
    SUBELEMENT,
    write_bundle,
)


def bake(**bundle_kwargs):
    """Write a synthetic bundle, then run the real receive path on it."""
    from bpy_speckle.converter.from_bundle.bundle_reader import read_bundle
    from bpy_speckle.converter.from_bundle.bundle_to_native import bake_bundle

    bpy.ops.wm.read_factory_settings(use_empty=True)
    with tempfile.TemporaryDirectory() as bundle_dir:
        write_bundle(bundle_dir, **bundle_kwargs)
        bundle = read_bundle(bundle_dir)
    return bake_bundle(bundle, "Received")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def children(collection) -> set:
    return {c.name for c in collection.children}


def homes(result, application_id: str) -> set:
    return {c.name for c in result.objects[application_id].users_collection}


def translation(x: float, y: float, z: float) -> str:
    return f"1,0,0,{x},0,1,0,{y},0,0,1,{z},0,0,0,1"


def navis_federation() -> None:
    """Two models become the outermost tier; the network parks under Systems.

    The duct appears both in its model and in its network — membership is
    additive, not a move.
    """
    result = bake(
        containers=[
            (1, "Supply Air", None, "Network"),
            (2, "hvac.nwc", None, "Model"),
            (3, "arch.nwc", None, "Model"),
        ],
        objects=["duct-1", "wall-1"],
        relations=[(IN_SYSTEM, 0, 1), (IN_MODEL, 0, 2), (IN_MODEL, 1, 3)],
    )
    check(
        children(result.root_collection) == {"hvac.nwc", "arch.nwc", "Systems"},
        f"model tier + Systems branch expected, got {children(result.root_collection)}",
    )
    check(homes(result, "duct-1") == {"hvac.nwc", "Supply Air"}, "duct multi-links")
    check(homes(result, "wall-1") == {"arch.nwc"}, "wall sits in its model")
    check(not result.unmapped_containers, "every axis here has a mapping")


def single_model_maps_onto_root() -> None:
    """One model adds no folder level, exactly like a lone authored root."""
    result = bake(
        containers=[(1, "site.nwc", None, "Model")],
        objects=["fence-1"],
        relations=[(IN_MODEL, 0, 1)],
    )
    check(
        children(result.root_collection) == set(),
        "a single model must not nest a redundant folder",
    )
    check(homes(result, "fence-1") == {"Received"}, "object sits at the root")


def rhino_groups_beside_layers() -> None:
    """The object keeps its layer AND its groups; groups nest under one branch."""
    result = bake(
        containers=[
            (2, "GroupA", None, "Group"),
            (3, "GroupB", 2, "Group"),
            (5, "Root", None, "Collection"),
            (6, "Layer1", 5, "Collection"),
        ],
        objects=["curve-1"],
        relations=[(IN_COLLECTION, 0, 6), (IN_GROUP, 0, 2), (IN_GROUP, 0, 3)],
    )
    root = result.root_collection
    check(
        children(root) == {"Layer1", "Groups"},
        f"authored tree + Groups branch expected, got {children(root)}",
    )
    groups = root.children["Groups"]
    check(children(groups) == {"GroupA"}, "top group under the branch")
    check(children(groups.children["GroupA"]) == {"GroupB"}, "groups nest")
    check(
        homes(result, "curve-1") == {"Layer1", "GroupA", "GroupB"},
        "layer plus both groups",
    )


def unknown_subtype_is_surfaced_not_baked() -> None:
    """A subtype we cannot map must be reported, never an empty folder."""
    result = bake(
        containers=[(1, "Mystery", None, "Zone")],
        objects=[],
        relations=[],
    )
    check(
        children(result.root_collection) == set(),
        "no misleading empty collection",
    )
    check(
        result.unmapped_containers == {"Zone": 1},
        f"tally expected, got {result.unmapped_containers}",
    )


def revit_parameter_paths_bake_as_groups() -> None:
    """A Revit parameter path is one flat eav key well past Blender's 63-byte
    IDProperty name limit; written verbatim it aborted the whole bake. The
    paths must come back as nested property groups, an over-long single
    segment is fitted rather than raised, and a scalar/subtree collision is
    tallied — never an exception.
    """
    keynote = (
        "properties.Parameters.Instance Parameters.Identity Data"
        ".Keynote Text With A Very Long Parameter Name"
    )
    length = "properties.Parameters.Instance Parameters.Dimensions.Length"
    result = bake(
        containers=[(1, "Root", None, "Collection")],
        objects=["wall-1"],
        relations=[(IN_COLLECTION, 0, 1)],
        properties=[
            (0, keynote, "K1"),
            (0, length, 3.5),
            (0, "properties." + "x" * 80, True),
            (0, "properties.A", 1.0),
            (0, "properties.A.B", 2.0),
        ],
    )
    wall = result.objects["wall-1"]
    params = wall["Parameters"]["Instance Parameters"]
    check(
        params["Identity Data"]["Keynote Text With A Very Long Parameter Name"] == "K1",
        "deep parameter path must bake as nested groups",
    )
    check(params["Dimensions"]["Length"] == 3.5, "sibling subtree survives")
    check(bool(wall["x" * 63]), "an over-long segment is fitted, value kept")
    check(wall["A"] == 1.0, "first arrival wins a scalar/subtree collision")
    check(
        result.dropped_properties == 1,
        f"the colliding path is tallied, got {result.dropped_properties}",
    )


def revit_subelement_parenting_preserves_world_transform() -> None:
    """Hierarchy metadata must not reinterpret absolute Revit placements.

    Revit family subelements are independent INSTANCE nodes whose transforms
    are already world-space. Reconstructing the SUBELEMENT hierarchy in Blender
    must preserve that world transform rather than applying the parent's
    placement a second time.
    """
    result = bake(
        containers=[],
        objects=["window", "frame", "metadata"],
        definitions=[(1, "window-definition"), (3, "frame-definition")],
        instances=[
            (2, 1, translation(20, 30, 0), "m"),
            (4, 3, translation(20, 31, 2), "m"),
        ],
        relations=[
            (DISPLAY_INSTANCE, 0, 2),
            (DISPLAY_INSTANCE, 1, 4),
            (SUBELEMENT, 0, 1),
            (SUBELEMENT, 0, 2),
        ],
    )
    bpy.context.view_layer.update()

    window = result.objects["window"]
    frame = result.objects["frame"]
    metadata = result.objects["metadata"]
    check(frame.parent is window, "SUBELEMENT hierarchy must be reconstructed")
    check(
        tuple(round(v, 6) for v in frame.matrix_world.translation) == (20.0, 31.0, 2.0),
        f"frame world transform must survive parenting, got {frame.matrix_world.translation}",
    )
    check(metadata.parent is window, "properties-only subelement must be parented")
    check(
        tuple(round(v, 6) for v in metadata.matrix_world.translation)
        == (20.0, 30.0, 0.0),
        "properties-only subelement must remain identity-local to its owner",
    )


SCENARIOS = [
    navis_federation,
    single_model_maps_onto_root,
    rhino_groups_beside_layers,
    unknown_subtype_is_surfaced_not_baked,
    revit_parameter_paths_bake_as_groups,
    revit_subelement_parenting_preserves_world_transform,
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
    raise SystemExit(main())
