# Headless publish harness

Runs the connector's publish conversion without the Blender GUI, an account, or
a server, then decodes the resulting parquet bundle into text you can read,
diff, and assert against.

```bash
tools/run_fixture.sh --all                    # every fixture, with assertions
tools/run_fixture.sh nested_collections       # one fixture
tools/run_fixture.sh --blend ~/scenes/x.blend # your own file, report only
tools/run_fixture.sh --blend ~/scenes/x.blend --objects Cube,Sphere
python tools/inspect_bundle.py <bundle_dir>   # re-read a bundle later
```

Exits nonzero when conversion fails or an expectation is unmet.

## Why this works

`publish_operation` mixes three concerns, but they separate cleanly:

| stage | needs | covered here |
| --- | --- | --- |
| `build_collection_hierarchy` — Blender state → Speckle `Collection` | bpy | yes |
| `BlenderBundleExporter` — `Collection` → parquet files | a directory | yes |
| `ArtifactPipeline` — parquet files → server | account + network | no |

Most conversion bugs live in the first two stages, so they can be caught
offline. What still needs a real publish: whether the server ingests the bundle
and whether the viewer renders it.

Importing `bpy_speckle` runs the add-on's own `ensure_dependencies`, which puts
`~/.config/Speckle/connector_installations/Blender <ver>/` on `sys.path`. The
harness therefore uses the exact specklepy build the GUI connector uses — no
separate test environment to drift.

## Writing a fixture

A fixture is a Python module in `tools/fixtures/` with a `build()` that
constructs a scene and returns the objects to publish, plus an optional
`EXPECT` dict. Scenes are code, not `.blend` blobs, so they diff in review.

```python
def build():
    obj = ...                                    # scene starts empty
    bpy.context.scene.collection.objects.link(obj)
    return [obj]

EXPECT = {"objects": 1, "geometry_types": {"mesh": 1}}
```

Omit `EXPECT` (or leave it empty) to get a report without assertions — useful
while working out what a new conversion path actually produces.

### EXPECT keys

Counts and name sets are compared exactly; `properties` and `eav_paths` are
subset checks, so a fixture pins what it cares about and tolerates unrelated
additions.

| key | meaning |
| --- | --- |
| `objects`, `geometries` | row counts |
| `geometry_types` | exact `{type: count}`, e.g. `{"mesh": 1, "curve": 1}` |
| `collections` | exact set of collection names |
| `collection_parents` | exact `{name: parent_name}`, root maps to `None` |
| `object_collections` | exact `{object_name: collection_name}` placement |
| `materials` | material count |
| `material_names` | exact set of material names |
| `definitions` | exact set of DEFINITION node names (instanced collections) |
| `instances` | INSTANCE node count (one per placement, nested included) |
| `definition_members` | exact `{definition_name: member_count}` |
| `instance_definitions` | exact `{placement_name: definition_name}`, via DISPLAY_INSTANCE |
| `instance_translations` | exact `{placement_name: [x, y, z]}` of the placement transform |
| `relations` | per-name counts: `DISPLAY`, `IN_COLLECTION`, `HAS_MATERIAL`, … |
| `subelements` | exact `{parent_name: [child_name, …]}`, children in ordinal order |
| `scene_views` | ordered view names |
| `eav_paths` | property paths that must exist |
| `properties` | `{object_name: {path: value}}`, subset |
| `receive_properties` | `{object_name: {key: value}}` a bake restores as user custom properties, **exact** per object |
| `receive_root_fields` | `{object_name: {path: value}}` of root schema scalars kept internal, **exact** per object |

The two `receive_*` keys are checked against the real `bundle_reader`, not
`inspect_bundle`'s raw-parquet view, and they compare exactly rather than as
subsets — their job is proving that nothing *extra* leaks into user custom
properties (ENG-9027). A fixture can also define `INJECT_ROOT_FIELDS =
{object_name: {path: value}}`; the harness appends those rows to the eav
tables after the export, simulating the bare root scalars a Rhino- or
Revit-produced bundle carries that Blender's own publish never writes.

Three things worth knowing when writing expectations:

- **Collection parentage is not a relation.** A `CONTAINER` node's `def_ref`
  points at its parent, so nesting three collections still yields one
  `IN_COLLECTION` edge per *object*. Assert `object_collections`, not edge
  counts — a count matches even when every object is in the wrong collection.
- **Integers arrive as floats.** The eav table writes numbers to
  `value_double`, so `obj["int_prop"] = 42` asserts as `42.0`.
- **`matrix_world` is lazy.** Setting `obj.location` in a fixture does not update
  `matrix_world` until `bpy.context.view_layer.update()`. Forget it and every
  object bakes at the origin — which passes a count-based expectation for
  entirely the wrong reason. Any fixture that places objects must call it.

## Limits

- `--blend` without `--objects` publishes the objects a user could actually
  select — `visible_get()`, not `scene.objects`. Objects in collections excluded
  from the view layer are reported and omitted, because the publish selection can
  never contain them. Pass `--objects` to override.
- Assertions only catch what a fixture thought to check. There are no committed
  golden snapshots, by choice — the bundle format is still moving on this
  branch and goldens would go red on every intentional change.
- Receive coverage stops at `bundle_reader` (the `receive_*` EXPECT keys);
  the bake into a real scene, the upload, and the UI operators are untested.
- `--factory-startup` means user preferences are skipped and `sys.path` is
  ordered so `import bpy_speckle` resolves to the working tree rather than the
  symlinked add-on install.
