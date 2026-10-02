---
name: run-fixture-harness
description: Validate a publish or receive change offline with the headless harness in tools/ — fixtures through Blender --background, synthetic-bundle receive tests, bundle inspection. Use before asking anyone to publish from the Blender GUI.
---

# Validate with the headless harness

The harness runs the real conversion + bundle export inside `Blender --background` and decodes the
parquet output into assertable text — no GUI, account or server. It exits nonzero when conversion
fails or an expectation is unmet. Reference for fixtures and the `EXPECT` / `EXPECT_RECEIVE`
vocabularies: `tools/README.md`.

## Publish path

```bash
tools/run_fixture.sh --all                        # all fixtures, with assertions
tools/run_fixture.sh nested_collections           # one fixture
tools/run_fixture.sh --blend ~/scenes/test.blend  # a real file, report only
tools/run_fixture.sh --blend ~/scenes/x.blend --objects Cube,Sphere
python tools/inspect_bundle.py <bundle_dir>       # re-read a bundle later
```

`--blend` without `--objects` publishes what a user could select (`visible_get()`), so objects in
collections excluded from the view layer are reported and omitted. `inspect_bundle.py` reads
geometry shard 0 only — fine for fixtures, wrong for a real multi-shard model.

## Receive path

The publish harness only produces Blender-shaped bundles. Cross-connector shapes (several
parentless CONTAINER axes, `IN_MODEL`/`IN_SYSTEM`/`IN_GROUP` membership, adversarial row order) are
fabricated with pyarrow in two tests:

```bash
uv run python tools/test_bundle_reader.py         # parquet -> specklepy Model join; no Blender
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  -noaudio --python tools/test_bundle_bake.py     # Model -> bake_bundle -> Outliner shape
```

A fixture can also declare `EXPECT_RECEIVE` (per instance loading mode) to round-trip its own
exported bundle through `read_bundle` + `Model` + `bake_bundle` — the code `load_operation` runs
after downloading.

## Adding a fixture

A fixture is a Python module in `tools/fixtures/` with a `build()` returning the objects to publish
and an optional `EXPECT` dict; scenes are code, never `.blend` blobs. Omit `EXPECT` to get a report
while working out what a new path produces. Any fixture that places objects must call
`bpy.context.view_layer.update()` — `matrix_world` is lazy, and without it every object bakes at
the origin while count-based expectations still pass.

## What stays manual

Whether the *server* ingests a bundle, the viewer renders it, and whether a real Revit/Navisworks
producer writes what the synthetic tables assume. Do that once per feature in Blender + viewer,
not per iteration. When the bundle format itself changes, also run the official validator:
`npm run validate -- <dir>` in the `speckle-bundle-spec` repo.

Never wire any of this into `.github/workflows/` — the harness is local-only by deliberate choice
while the bundle format is moving; PR CI runs pre-commit (ruff) only.
