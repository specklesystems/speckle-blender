"""Round-trips an exported bundle back through the receive bake, headlessly.

The publish harness stops at parquet on disk; this picks those files up with
``read_bundle`` + ``bake_bundle`` — the exact code path ``load_operation`` runs
after downloading — and reduces the resulting scene to facts a fixture can
assert: which collection every object landed in, what stayed an instancing
empty, and where things sit in world space.

The facts deliberately describe **what the user sees** rather than the bake's
internals: objects reachable from the scene root, and only those. A definition
"library" collection is never linked into the scene, so its members are
invisible here — exactly as they are in the outliner.

Unlike the publish summary this needs ``bpy``, so it runs inside the same
headless Blender session as the export, not as a standalone script.
"""

from typing import Any, Dict, List


def bake_and_probe(bundle_dir: str, instance_loading_mode: str) -> Dict[str, Any]:
    """Receive the bundle into a fresh empty scene and describe the result."""
    import bpy

    from bpy_speckle.converter.from_bundle.bundle_reader import read_bundle
    from bpy_speckle.converter.from_bundle.bundle_to_native import bake_bundle

    # a fresh scene per mode keeps Blender's .001 dedup suffixes deterministic
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bundle = read_bundle(bundle_dir)
    bake_bundle(bundle, "Received", instance_loading_mode)
    # parented copies get their matrix_world from the depsgraph, not at link time
    bpy.context.view_layer.update()

    collections = _scene_collections()
    reachable = {c.name for c in collections}
    objects = sorted(
        {obj for c in collections for obj in c.objects}, key=lambda o: o.name
    )

    return {
        "collections": sorted(reachable),
        "object_collections": {
            obj.name: sorted(
                c.name for c in obj.users_collection if c.name in reachable
            )
            for obj in objects
        },
        "collection_instances": sorted(
            obj.name for obj in objects if obj.instance_type == "COLLECTION"
        ),
        "parents": {
            obj.name: obj.parent.name if obj.parent else None for obj in objects
        },
        "translations": {
            obj.name: [round(v, 3) for v in obj.matrix_world.translation]
            for obj in objects
        },
    }


def _scene_collections() -> List[Any]:
    """Every collection reachable from the scene root, root first."""
    import bpy

    found: List[Any] = []

    def walk(collection: Any) -> None:
        found.append(collection)
        for child in collection.children:
            walk(child)

    walk(bpy.context.scene.collection)
    return found


def format_report(mode: str, facts: Dict[str, Any]) -> str:
    lines = [f"--- receive [{mode}]"]
    lines.append(f"  collections: {facts['collections']}")
    for name, colls in facts["object_collections"].items():
        parent = facts["parents"][name]
        xyz = facts["translations"][name]
        instanced = (
            " [COLLECTION instance]" if name in facts["collection_instances"] else ""
        )
        lines.append(f"  {name}: in {colls}, parent={parent}, at {xyz}{instanced}")
    return "\n".join(lines)


def check(facts: Dict[str, Any], expect: Dict[str, Any]) -> List[str]:
    """Compare probe facts against a fixture's per-mode EXPECT_RECEIVE block.

    Scene structure keys are exact — an escaped object is precisely the kind of
    *extra* entry a subset check would wave through. ``parents`` and
    ``translations`` are subset checks so a fixture pins the objects it cares
    about.
    """
    failures: List[str] = []

    def eq(label: str, actual: Any, wanted: Any) -> None:
        if actual != wanted:
            failures.append(f"{label}: expected {wanted!r}, got {actual!r}")

    for key, wanted in expect.items():
        if key == "collections":
            eq("collections", facts["collections"], sorted(wanted))
        elif key == "object_collections":
            eq(
                "object_collections",
                facts["object_collections"],
                {k: sorted(v) for k, v in dict(wanted).items()},
            )
        elif key == "collection_instances":
            eq("collection_instances", facts["collection_instances"], sorted(wanted))
        elif key == "parents":
            for name, parent in dict(wanted).items():
                eq(f"parents[{name}]", facts["parents"].get(name), parent)
        elif key == "translations":
            for name, xyz in dict(wanted).items():
                eq(
                    f"translations[{name}]",
                    facts["translations"].get(name),
                    [round(float(v), 3) for v in xyz],
                )
        else:
            failures.append(f"unknown EXPECT_RECEIVE key {key!r}")

    return failures
