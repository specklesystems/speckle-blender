# Parquet bundle migration regression report

Date: 2026-07-29
Branch: `bilal/parquet-bundle-migration` at `fb5ec985c464`
Baseline: `main` at `cc2466dec050`
Diff basis: `git diff main...HEAD` (the merge-base is the same `main` commit)
Bundle specification reviewed: local `speckle-bundle-spec` `main` at
`2af96ef`; the catalog contract was also checked against the locally available
`origin/main` at `93fa141` and is unchanged for the findings below.

## Verdict

**Not regression-safe for release.**

The publish fixtures are healthy and the generated files pass the current
official validator, but there are two release blockers:

1. The locked production dependency does not contain `specklepy.bundle`, so the
   shipped connector does not activate parquet publish or receive.
2. Bundles produced by the development dependency and the new Blender reader use
   abbreviated catalog schemas that are incompatible with the official v5
   specification.

There are also reproducible receive regressions in linked-duplicate placement
and custom-property reconstruction, plus untested cross-connector grouping and
large-file download risks.

## Severity summary

| ID | Severity | Area | Summary |
| --- | --- | --- | --- |
| R1 | Critical | Packaging | Locked `specklepy` has no bundle API; migration is inactive in a production-like install |
| R2 | Critical | Interoperability | Producer and reader use catalog schemas that do not match bundle-spec v5 |
| R3 | High | Receive | **Resolved (ENG-9025)** — `LINKED_DUPLICATES` leaked children into the scene root and retained nested collection instances |
| R4 | High | Receive | **Resolved** (ENG-9026) — all CONTAINER subtypes are read and each membership axis bakes to a documented mapping |
| R5 | High | Scalability | Every parquet artifact is buffered completely in memory before it is written |
| R6 | Medium | Receive | ~~Root schema fields are restored as user custom properties~~ **Resolved** (ENG-9027) |
| R7 | Medium | Error handling | Non-404 artifact probe failures silently fall back to a receive path known to fail for bundle versions |
| R8 | Medium | Documentation | The migration document no longer describes the branch that will be reviewed or released |

## Detailed findings

### R1 — Critical: the locked runtime cannot publish or receive bundles

`pyproject.toml:10` permits `specklepy>=2026.6.0`, and `uv.lock:828-844` locks
exactly `2026.6.0`. That release does not contain `specklepy.bundle`.

Reproduction:

```text
$ uv run --frozen python -c \
  "import importlib.metadata as m; print(m.version('specklepy')); import specklepy.bundle"
specklepy 2026.6.0
ModuleNotFoundError: No module named 'specklepy.bundle'
```

Impact:

- `is_bundle_send_available()` returns false, so publishing silently stays on
  the classic JSON path.
- `is_bundle_receive_available()` returns false. A bundle-published version then
  falls through to `operations.receive()` with the synthetic
  `binary-{versionId}` object id, which the branch documentation correctly says
  cannot resolve.
- The committed fixture suite only passes because the local Blender installation
  contains a manually installed `specklepy 2026.6.1.dev3`.

Required action: pin a released `specklepy` version that contains the producer,
reader, and expected bundle-spec pin, or explicitly package a reviewed commit.
The minimum version must be enforced rather than left to runtime feature
detection.

### R2 — Critical: the catalog contract is incompatible with the official spec

The official v5 source of truth defines:

- `rel_types(id, name, src_ns, dst_ns, status, emitted_by, ord_semantics,
  description, why)` in `speckle-bundle-spec/spec/bundle-spec.sql:188-198`.
- `node_kinds(id, name, status, columns, subtype_values, description, why)` in
  `speckle-bundle-spec/spec/bundle-spec.sql:226-234`.

The branch's generated fixture bundles instead contain:

```text
rel_types : rel, name, src_ns, dst_ns
node_kinds: kind, name
```

The new reader is coupled to those abbreviated, non-spec names:

- `bundle_reader.py:223-224` requires `node_kinds["kind"]`.
- `bundle_reader.py:268-269` requires `rel_types["rel"]`.

Consequences are bidirectional:

- A spec-conforming producer that writes `id` causes this Blender reader to
  raise `KeyError`.
- A spec-conforming consumer that expects `id` and the semantic catalog columns
  cannot consume Blender's catalog as specified.
- Both sides stamp `schema_version = 5`, so the incompatibility cannot be
  detected from the version number.

The EAV output also violates the official rule at
`bundle-spec.sql:54`, “Exactly one of
value_string/value_double/value_boolean is set.” A fixture row for integer `42`
contains both `value_string = "42"` and `value_double = 42.0`; a boolean row
contains both string and boolean values.

The official validator passed all of these bundles because it currently does not
validate the catalog table shapes or EAV value exclusivity. Therefore
`docs/parquet-bundle-migration.md:56-58` is accurate only for the subset the
validator checks, not full semantic conformance.

Required action:

1. Pin Blender and specklepy to the same bundle-spec artifact/hash.
2. Emit and read the official catalog shapes.
3. Extend the official validator to check catalog schemas and EAV exclusivity.
4. Add one test bundle generated directly from the official schemas so producer
   and reader cannot drift together unnoticed.

### R3 — High: linked-duplicate receive escapes the imported model collection

**Resolved (ENG-9025).** `_bake_placement` now returns every object it creates
and the caller links them into the target collection; nested placements are
expanded recursively under `LINKED_DUPLICATES` instead of being copied as
instancing empties. `EXPECT_RECEIVE` assertions in `collection_instances` and
`nested_instances` pin top-level and nested behaviour for both loading modes.
The original report follows.

In `bundle_to_native.py:866-874`, the placement parent is returned to the caller
and linked to the imported target collection, but each copied definition member
is linked directly to `bpy.context.scene.collection`.

Reproduction against the committed `collection_instances` fixture:

```text
PLACEMENT_COLLECTIONS ['Roundtrip']
CHILD_COLLECTIONS [('Widget.001', ['Scene Collection'])]
```

Deleting or unlinking the imported model collection therefore leaves its copied
children in the scene root. It also breaks the expected Outliner hierarchy.

Nested instances do not honor `LINKED_DUPLICATES` either.
`_build_definitions()` always creates collection-instance empties at
`bundle_to_native.py:827-840`, regardless of the selected mode. Reproduction
against `nested_instances`:

```text
COLLECTION_INSTANCE_OBJECTS [
  ('Leaf.001', 'COLLECTION'),
  ('Leaf.002', 'COLLECTION')
]
```

The classic receive implementation links linked duplicates to the passed root
collection and recursively applies the requested mode
(`to_native.py:1421-1503`).

Required action: pass the target collection and loading mode through definition
baking, link all copies to that target, and add assertions for both top-level and
nested linked-duplicate receives.

### R4 — High: cross-connector grouping is reconstructed incorrectly

Bundle-spec v5 makes CONTAINER polymorphic; `subtype` is the discriminator for
`Collection`, `Model`, `MEP System`, `Network`, and `Group`. Membership uses
different relations (`IN_COLLECTION`, `IN_MODEL`, `IN_SYSTEM`, and `IN_GROUP`).
See:

- `speckle-bundle-spec/CONTEXT.md`, “CONTAINER” and “subtype”.
- `speckle-bundle-spec/docs/reference.md`, relations 10, 11, 14, and 17.

The reader:

- treats every CONTAINER as `BundleCollection` without reading `subtype`
  (`bundle_reader.py:230-237`);
- only resolves `IN_COLLECTION` (`bundle_reader.py:292-295`);
- chooses the first parentless CONTAINER as the root
  (`bundle_reader.py:117-123`).

On Revit/Navisworks/Rhino bundles this can select a model, system, network, or
group as the Blender collection root, create spurious empty collections, and
drop the grouping relations that actually place objects in them.

Required action: model each grouping axis explicitly, choose the authored
collection root by subtype/relation rather than iteration order, and define how
non-collection axes map into Blender.

**Resolved** (ENG-9026): the reader keeps `subtype` on `BundleContainer` and
resolves all four membership relations; the root is the parentless
`CONTAINER(Collection)` with the lowest node id; the bake maps each axis per
the contract in `parquet-bundle-migration.md` ("Container axes map per
subtype") and tallies unknown subtypes instead of baking empty folders.
Covered by `tools/test_bundle_reader.py` and `tools/test_bundle_bake.py`.

### R5 — High: artifact downloads buffer whole parquet shards in RAM

`bundle_receive.py:109-112` calls `client.get(url)`, materializes
`response.content`, then writes it. The bundle format deliberately shards only
after a geometry file reaches roughly 1.5 GiB, so a valid bundle can require at
least that much additional memory per download.

This defeats a major advantage of the parquet path for large models and can
terminate Blender before parsing begins.

Required action: use an HTTP streaming response and write bounded chunks. Verify
with a sparse or generated large artifact and measure peak RSS.

### R6 — Medium: root schema fields become user custom properties

`bundle_reader.py:334-361` documents that only the `properties.` subtree is user
data, but every root field except `name` and `speckle_type` is inserted into
`BundleObject.properties`. `_apply_properties()` then writes it to Blender.

Reproduction against `cube_with_props`:

```text
ROUNDTRIP_PROPERTIES {
  'type': 'MESH',
  'properties.text_prop': 'hello',
  ...
}

BAKED_KEYS [
  'applicationId', 'bool_prop', 'float_prop', 'int_prop',
  'speckle_type', 'text_prop', 'type'
]
BAKED_TYPE_PROP MESH
```

The schema field `type` is now indistinguishable from user-authored custom data.
Other producers' root EAV fields would leak the same way.

Required action: lift all recognized root fields into typed attributes and only
round-trip paths beginning with `properties.`.

**Resolved** (ENG-9027): `_read_properties` now routes only `properties.*`
paths into `BundleObject.properties`; every other root scalar goes to an
internal `root_fields` dict that the bake never restores. On the publish side
`extract_custom_properties` skips `applicationId`/`speckle_type` (both receive
paths bake those deliberately), so a receive-and-republish cycle introduces no
new user properties. Pinned by the `receive_properties` /
`receive_root_fields` expectations in the `cube_with_props` fixture, which
also injects synthetic cross-producer root fields.

### R7 — Medium: artifact probe errors are masked by classic fallback

`bundle_receive.py:58-76` converts network failures, authorization failures,
server errors, invalid JSON, and 404 into the same empty result. `load_operation`
then uses classic receive.

For a bundle version, classic receive is known to fail because the
`binary-{versionId}` sentinel is not an object row. An expired token or temporary
v2 outage is therefore reported later as an unrelated object 404.

Required action: fall back only for the explicit “no bundle/unsupported
endpoint” response contract. Propagate authentication, server, payload, and
transport failures with the original context.

### R8 — Medium: migration documentation is stale

`docs/parquet-bundle-migration.md` says:

- ingestion is created before conversion (`:13-18`), while
  `publish_operation.py:209-220` converts first;
- the existing conversion pipeline is reused unchanged (`:16-18`), while this
  branch substantially expands conversion behavior;
- receive remains classic (`:52`), while four new modules/paths implement bundle
  receive;
- exporter output passes the official validator (`:56-58`) without documenting
  the validator's semantic gaps.

This makes the branch's own spec unsuitable as a release or review contract.

Required action: update the migration document after the runtime and official
schema are aligned.

## Known behavioral regressions and accepted constraints

These are already acknowledged in code or branch documentation, but they remain
behavior changes compared with `main` when bundle publishing becomes the default:

- Version messages are discarded on bundle publish
  (`docs/parquet-bundle-migration.md:49-51`).
- List-valued custom properties are silently omitted by the bundle EAV walker
  (`CLAUDE.md`, “Lists never serialize on the bundle path”).
- Mesh/curve data-block custom properties do not reach EAV; only object-level
  properties do (`to_speckle.py:12-26` and `CLAUDE.md`).
- A member published both standalone and inside a definition comes back only in
  the definition collection (`CLAUDE.md`, receive known gap).
- Non-uniform NURBS knot vectors cannot be reconstructed exactly through
  Blender's Python API (`CLAUDE.md`, receive gotchas).

These should be explicit release notes or resolved before claiming classic-path
parity.

## Verification performed

### Passed

- `tools/run_fixture.sh --all`
  - 12 fixture scenes executed in Blender 4.3.
  - 11 fixtures had assertions and passed.
  - `duplicate_materials` was report-only because `EXPECT = {}`.
- Official validator:
  - all 12 emitted fixture bundles returned `validate: PASS`;
  - required files, known relation/kind ids, selected table columns, and dense
    object/node/geometry K-spaces passed.
- `uv run pre-commit run --all-files`
  - Ruff lint, Ruff format, EOF, and trailing-whitespace checks passed.
- Focused Blender receive probes:
  - reproduced root-property leakage;
  - reproduced linked-duplicate collection leakage;
  - reproduced nested collection instances under `LINKED_DUPLICATES`.

### Not covered

- Actual server sign/upload/complete flow.
- Classic-send fallback semantic parity.
- Bundle receive through the real artifact endpoint.
- Receive assertions in the committed harness.
- Cross-producer bundles with Model/System/Network/Group containers.
- Large-file memory behavior.
- Text/FONT conversion through real Blender.
- UI operator behavior from the merged dialog-width changes.

## Regression test gaps

1. Add a Blender-free `bundle_reader` suite using official-spec parquet tables,
   not tables emitted by the same specklepy implementation.
2. Add Blender round-trip fixtures for mesh, curves, materials, properties,
   collection instances, nested instances, subelements, and all loading modes.
3. Turn `duplicate_materials.EXPECT` into material-name and geometry-material
   assertions.
4. Add a FONT fixture because the new path calls Blender `to_mesh()`.
5. Add contract tests for artifact endpoint status handling and streamed
   downloads.
6. Validate a freshly emitted bundle in an automated producer test. Keep the
   current local Blender harness out of CI if desired, but validate a
   deterministic, Blender-free producer fixture in CI.

## Standards-axis review

- **Hard:** the complete parquet receive path has no regression coverage.
  `.github/CONTRIBUTING.md:23-35` requires tests for fixes and features, while
  `tools/README.md` explicitly says receive is untested.
- **Hard:** FONT conversion touches `to_mesh()` but has no Blender fixture,
  contrary to the real-Blender validation rule in `CLAUDE.md`.
- **Hard:** `duplicate_materials.py` has `EXPECT = {}`, so a known
  material-identity regression is not asserted.
- **Judgment call:** the branch also includes unrelated popup-width changes and
  a called but no-op `invalidate_downstream_selection()` helper, increasing
  regression surface outside the parquet migration.

## Spec-axis review

- **High:** the reader expects `rel`/`kind` catalog keys while the official spec
  defines `id`; it cannot read a conforming v5 catalog.
- **High:** emitted catalogs and EAV value population are not semantically
  conformant even though the current validator passes them.
- **Medium:** receive was outside the written migration scope, and its CONTAINER
  implementation is incomplete for the official grouping vocabulary.
- **Medium:** no automated producer conformance gate validates a freshly emitted
  bundle against the official specification.

## Recommended release gate

Do not merge/release the migration until R1 and R2 are closed. Before declaring
regression parity, also require:

1. passing asserted publish and receive round trips for both instance modes;
2. one official-spec cross-producer fixture;
3. streamed artifact download coverage;
4. explicit product acceptance of the known data-loss constraints;
5. an updated migration contract and release notes.
