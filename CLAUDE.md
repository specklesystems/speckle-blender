# speckle-blender

Next-gen Speckle connector for Blender, shipped as a Blender extension. The
add-on package is `bpy_speckle/` — that directory is the entire product, and it
is the only thing `release.yml` zips.

```
bpy_speckle/
  connector/
    ui/                 panels and dialogs (SPECKLE_PT_*, SPECKLE_OT_*)
    blender_operators/  operator classes bound to UI buttons
    operations/         publish_operation.py, load_operation.py, bundle_publish.py
    utils/              account/project/model/version managers, property groups
  converter/
    to_speckle/         Blender -> Speckle (per-type modules + bundle_exporter.py)
    to_native.py        Speckle -> Blender
  installer.py          bootstraps specklepy into the connector install path
tools/                  local dev harness — NOT shipped, NOT run in CI
```

## Local dev setup

The add-on is used from the working tree via a symlink, so edits take effect on
Blender restart with no reinstall:

```
~/Library/Application Support/Blender/4.3/extensions/user_default/speckle_blender_addon
  -> <repo>/bpy_speckle
```

Runtime dependencies (specklepy, pyarrow, …) live in
`~/.config/Speckle/connector_installations/Blender <ver>/`, installed with
Blender's bundled Python. Importing `bpy_speckle` runs `ensure_dependencies()`,
which prepends that directory to `sys.path`.

`bpy_speckle/requirements.txt` is **gitignored and deliberately absent** in a
dev checkout — the startup installer skips installation when it is missing.
`pyproject.toml` + `uv.lock` are the committed truth; `export_dependencies.sh`
generates the requirements file at package time. Do not commit one.

After changing a local specklepy checkout, reinstall it into the deps path:

```bash
pip install --no-deps -t "~/.config/Speckle/connector_installations/Blender 4.3" <specklepy repo>
```

## Validating changes — local only

Run the headless harness. It executes the real conversion + bundle export inside
`Blender --background` and decodes the parquet output into assertable text, with
no GUI, account, or server:

```bash
tools/run_fixture.sh --all                        # all fixtures, with assertions
tools/run_fixture.sh nested_collections           # one fixture
tools/run_fixture.sh --blend ~/scenes/test.blend  # a real file, report only
python tools/inspect_bundle.py <bundle_dir>       # re-read a bundle
```

**This is a local development tool by deliberate choice. Do not add it to
`.github/workflows/`.** PR CI runs pre-commit (ruff) only, and should stay that
way; the bundle format is still moving and CI assertions would churn. Ruff does
lint `tools/` via `--all-files`, which is intended — that is linting, not the
harness running.

Prefer this over asking the user to publish manually. Reserve the manual
Blender + viewer check for what the harness cannot cover: whether the *server*
ingests a bundle and the viewer renders it. Once per feature, not per iteration.

See `tools/README.md` for the `EXPECT` vocabulary and how to add a fixture.
Fixtures are scenes-as-code in `tools/fixtures/`, never `.blend` blobs, so they
diff in review.

## Publish architecture

`publish_operation()` picks between three paths, in preference order:

1. **Parquet bundle** (Speckle 4.0, bundle-spec v5) — requires `specklepy.bundle`
   importable *and* a server that pre-allocates a `versionId` on the ingestion.
   The version id names the bundle files, so the ingestion must exist before
   conversion. The v2 `complete` call creates the version itself; no
   `model_ingestion.complete` follows, and version messages are dropped (no
   field in the payload — a server-side API gap).
2. **Model ingestion + classic send** — JSON detached objects, then `complete`.
3. **`version.create`** — legacy, when the server has no ingestion support.

Both fallbacks are feature-detected, never assumed. `SPECKLE_BLENDER_BUNDLE=0`
force-disables the bundle path. The **receive** path is still classic
`operations.receive`.

The pipeline separates cleanly, which is what makes offline testing possible:
`build_collection_hierarchy` (Blender → Speckle `Collection`) and
`BlenderBundleExporter` (→ parquet on disk) need no network. Only
`ArtifactPipeline` in `bundle_publish.py` talks to a server.

## Bundle gotchas

- Blender uses the **direct-display dialect** (same as Rhino): an ordinary
  object's `displayValue` is already in world coordinates, so it links straight
  to geometry with a `DISPLAY` edge.
- **Geometry ids are keyed on the object, never the data-block.** World-baked
  geometry needs an object-scoped identity, or linked duplicates collide and
  the exporter's id-keyed cache serves them all the first copy's mesh. See
  `get_submesh_id` / `get_curve_element_id`.
- **Collection instances are the one exception to direct-display**, and use the
  same DEFINITION/INSTANCE layer as the C# connectors' blocks:
  `instance_unpacker.py` turns a placement empty into an `InstanceProxy` +
  `InstanceDefinitionProxy` (Rhino's `RhinoInstanceUnpacker`), and
  `bundle_exporter.py` translates those to nodes (Rhino's
  `RhinoArtifactRootObjectBuilder`). Producing proxies rather than nodes is what
  lets the classic send path round-trip with the existing `to_native` receive.
  - The placement transform is `empty.matrix_world @
    Translation(-collection.instance_offset)` — members bake their own
    `matrix_world` as definition-local geometry, so the collection pivot has to
    come back out of the placement.
  - **Definition members are usually real scene objects too**, unlike a Rhino
    block's members. A member is suppressed from the scene tree (no
    `IN_COLLECTION`, no `DISPLAY`) only when the user did *not* select it in its
    own right; the unpacker says which via the root's `definitionOnlyObjects`.
  - A collection holding *only* definition-only members emits no `CONTAINER`
    node — otherwise the usual excluded-from-the-view-layer "library"
    collection leaves an empty folder in the viewer's scene tree.
  - Known gap: `load_operation` skips every object listed in a definition, so a
    member published as *both* standalone and a definition member comes back
    only inside its definition collection.
  - Not yet handled: `instance_type` in `{VERTS, FACES}` and geometry-nodes
    instancing, which only exist in the evaluated depsgraph.
- **Metaballs publish per family, not per object**, and are the only type using
  the `SUBELEMENT` edge. Blender sums the fields of every metaball sharing a
  base name (`Mball`, `Mball.001`) and polygonizes one merged isosurface onto
  the **basis** — the lowest numeric suffix, where an unsuffixed name sorts
  lowest. The basis becomes the family object carrying the blob; its siblings
  become properties-only SUBELEMENT children, keeping their own
  `IN_COLLECTION` edge. `metaball_unpacker.py` assigns the roles,
  `bundle_exporter._emit_subelements` emits the edges.
  - This ports Revit's curtain wall (`ElementUnpacker` +
    `RevitArtifactRootObjectBuilder.EmitChild`) **inverted**: there the parent
    is an empty container and the children own the geometry; here the basis
    owns all of it and the children own none. A metaball's isosurface is
    continuous across contributors, so per-member geometry does not exist even
    in principle.
  - A non-basis member evaluates to an *empty mesh*, not an error, and only the
    basis is worth tessellating. Hidden members contribute no field at all.
  - The merged mesh is in **basis-local** space with siblings baked in, so
    `mesh_to_speckle_meshes(basis, …)` recovers world coordinates. A
    non-uniformly scaled basis genuinely deforms the blob, matching the
    viewport.
  - Selecting a member without its basis publishes the *whole* family (the only
    way geometry exists) and logs that it did. Not yet handled: `MetaElement`
    granularity — elements have no stable identity to key an applicationId on.
- **Only object-level properties reach the eav table.** Data-block (mesh/curve)
  custom properties are dropped by SGEO geometry encoding. There is an open
  decision in `merge_data_block_properties()` in `to_speckle/to_speckle.py`
  about whether that should change; the current default is object-only.
- **Lists never serialize on the bundle path.** specklepy's eav walker skips
  list values (C# parity), so arrays only survive a classic send.
- **Collection parentage is not a relation.** A `CONTAINER` node's `def_ref`
  points at its parent, so nesting N collections still yields one
  `IN_COLLECTION` edge per *object*. Assert placement, not edge counts.
- **Integers become floats.** The eav table populates `value_double`, so
  `obj["n"] = 42` reads back as `42.0`.
- Curves split by shape: `curve_may_have_volume()` sends solids as tessellated
  meshes and keeps genuine wires as exact splines.
- Validate exporter output against the official validator when the format
  changes: `npm run validate -- <dir>` in the `speckle-bundle-spec` repo.

## Conventions

- Ruff for lint + format, enforced by pre-commit (`uv run pre-commit install`).
  No test framework — the harness in `tools/` fills that role locally.
- `bpy_speckle/__init__.py` carries `bl_info` and registers every class; new
  operators and panels must be added to its registration lists.
- Type-checking against `fake-bpy-module-latest` gives autocomplete only; it
  cannot evaluate a depsgraph, so anything touching modifiers or `to_mesh()`
  must be exercised through real Blender.
