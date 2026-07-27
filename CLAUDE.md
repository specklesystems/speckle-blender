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

- Blender uses the **direct-display dialect** (same as Rhino): every
  `displayValue` is already in world coordinates, so objects link straight to
  geometry with `DISPLAY` edges. No DEFINITION/INSTANCE layer.
- **Geometry ids are keyed on the object, never the data-block.** World-baked
  geometry needs an object-scoped identity, or linked duplicates collide and
  the exporter's id-keyed cache serves them all the first copy's mesh. See
  `get_submesh_id` / `get_curve_element_id`.
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
