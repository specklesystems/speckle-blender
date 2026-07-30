# Parquet bundle migration (Speckle 4.0, bundle-spec v5)

This document is the review and release contract for Blender's move to the
parquet bundle schema
([speckle-bundle-spec](https://github.com/specklesystems/speckle-bundle-spec),
`SCHEMA_VERSION = 5`). It describes what the branch actually implements, what it
deliberately does not, and what must close before release.

The migration now covers **both directions**. Publish writes a bundle; receive
reads one and bakes it straight into `bpy.data`. Neither direction is reachable
with the currently locked `specklepy` — see [Packaging](#packaging-requirements),
which is a release blocker rather than a runtime nicety.

Both directions are feature-detected and fall back to the classic JSON path, so
the connector keeps working on older servers and older specklepy builds.
`SPECKLE_BLENDER_BUNDLE=0` force-disables the bundle on both sides.

## Publish

### Decision path

`publish_operation()` (`connector/operations/publish_operation.py`) picks between
three paths, in preference order:

```
publish_operation(context, objects, version_message, apply_modifiers)
│
├─ 1. _check_use_model_ingestion_send()                      [network]
│     model.can_create_model_ingestion() + ensure_authorised()
│     GraphQLException -> no ingestion support
│
├─ 2. build_collection_hierarchy()                           [no network]
│     unpack_instances -> unpack_metaballs -> analyze_collection_structure
│     -> convert_to_speckle per object -> Speckle `Collection` tree
│     -> renderMaterialProxies attached to the root
│     returns None (nothing converted) -> abort, no ingestion created
│
├─ 3a. ingestion supported -> _send_via_ingestion()
│      model_ingestion.create()          -> ingestion_id
│      model_ingestion.start_processing()
│      is_bundle_send_available()        specklepy.bundle importable, env not 0
│      fetch_pre_allocated_version_id()  project.ingestion.versionId (v2 only)
│      │
│      ├─ version id present -> PARQUET BUNDLE
│      │    BlenderBundleExporter(tmpdir, version_id).export(root)
│      │    ArtifactPipeline(...).upload_dir()
│      │      sign -> presigned PUT per file -> complete
│      │    `complete` CREATES the version; no model_ingestion.complete follows
│      │
│      └─ otherwise -> CLASSIC SEND VIA INGESTION
│           operations.send(root, [ServerTransport])
│           model_ingestion.complete(ModelIngestionSuccessInput)
│
│      any exception -> model_ingestion.fail_with_error(), then re-raise
│
└─ 3b. no ingestion support -> LEGACY
       operations.send(...) -> version.create(CreateVersionInput)
```

### When the ingestion is created, and why

Conversion runs **first**, at step 2, before the ingestion exists. Only the
*bundle write* needs the pre-allocated version id: it is the exporter's
`base_name`, and every parquet file is named `{versionId}.{table}.parquet`. So
the ordering constraint is

> ingestion created → version id known → parquet files can be named

not "ingestion before conversion". Nothing in `build_collection_hierarchy` —
`convert_to_speckle`, geometry baking, material proxies — needs a version id.

Two consequences of this order are worth keeping:

- The permission probe (step 1) runs before conversion, so an unauthorised user
  is told immediately rather than after waiting through a large scene.
- The ingestion is created only after conversion has produced something. A scene
  that converts to nothing returns at `publish_operation.py:214` and leaves no
  orphaned in-progress ingestion on the server.

Do not "fix" the order to match the older description; the older description was
the mistake.

### What the exporter emits

`BlenderBundleExporter` (`converter/to_speckle/bundle_exporter.py`) walks the
converted `Collection` tree and drives specklepy's `ObjectsArtifactPipeline`:

| Blender / Speckle | Bundle |
| --- | --- |
| `BlenderObject` | row in `eav.objects`, properties flattened into `eav.eav` |
| `displayValue` meshes & curves | SGEO blobs in `geometries` + `DISPLAY` edges |
| Blender collections | `CONTAINER` nodes (subtype `Collection`) + `IN_COLLECTION` edges |
| materials | `MATERIAL` nodes + `HAS_MATERIAL` edges (geometry → material) |
| collection instances | `DEFINITION` + `INSTANCE` nodes, `DISPLAY_INSTANCE` / `DEFINES` / `DEFINES_INSTANCE` |
| metaball families | basis carries the merged blob, siblings become `SUBELEMENT` children |

Blender uses the **direct-display dialect** (same as Rhino): an ordinary object's
`displayValue` is already in world coordinates and links straight to geometry.
Collection instances are the one exception and use the DEFINITION/INSTANCE layer
that the C# connectors use for blocks. The default scene view groups by
`IN_COLLECTION`. See `CLAUDE.md` ("Bundle gotchas") for the per-type rules.

## Shared conversion changes

These changes live in `converter/to_speckle/` and therefore apply to the
**classic fallback too**, not only to the bundle. They are the part of the branch
most likely to be missed in review, because a reviewer testing on a server
without v2 endpoints still gets all of them.

1. **New publishable object types.** `SUPPORTED_OBJECT_TYPES` is now
   `{MESH, CURVE, SURFACE, FONT, EMPTY, META}`. On `main` only `MESH` and
   `CURVE` produced a `BlenderObject`; every other type fell out as `None`.
   - `SURFACE` → tessellated meshes (`surface_to_speckle.py`). SGEO has no
     Surface primitive, so there is no exact route on either path.
   - `FONT` → tessellated glyph meshes plus the string and layout settings as
     properties (`text_to_speckle.py`).
   - `EMPTY` → the one type that publishes with no geometry at all
     (`empty_to_speckle.py`); it is a transform, a name and its properties.
   - `META` → per *family*, not per object (`metaball_unpacker.py`).
2. **Custom properties** (`extract_custom_properties`). Object-level and
   data-block-level properties are both read. `merge_data_block_properties()` in
   `to_speckle.py` currently returns object-level only — an open decision, see
   its docstring. Data-block properties are additionally applied to the
   `displayValue` geometry via `apply_cached_properties`, which serialises on a
   classic send and is dropped by SGEO geometry encoding on the bundle.
   `extract_custom_properties` skips `applicationId` and `speckle_type` — both
   receive paths bake those onto objects as internal bookkeeping, and
   re-collecting them would mint `properties.applicationId` /
   `properties.speckle_type` on every receive-and-republish cycle (ENG-9027). A
   user property authored under either name is consequently not publishable.
3. **Curves split by shape.** `curve_may_have_volume()` sends bevelled, extruded
   or filled curves as tessellated meshes and keeps genuine wires as exact
   splines. This changes classic-path output for solid curves, which previously
   went through a single code path.
4. **Geometry applicationIds are keyed on the object, not the data-block.**
   `Mesh:{data.name_full}_mat{i}` → `{objectId}:mat{i}`, and
   `Curve:{data.name_full}` → `{objectId}:curve{i}`. Required because
   world-baked geometry means two objects sharing a data-block describe
   *different* geometry; the old key made linked duplicates collide. **This
   changes ids on the classic path as well**, so anything keyed on the previous
   scheme (diffing against pre-migration versions, stored selections) will not
   match across the migration.
5. **Instance unpacking** (`instance_unpacker.py`) runs on both paths, producing
   `InstanceProxy` / `InstanceDefinitionProxy` rather than bundle nodes, which is
   what lets the classic path still round-trip through the existing `to_native`.
   It also *expands the publish set*: members of an instanced collection convert
   even when the user selected only the placement empty.
6. **Metaball unpacking** runs on both paths. The basis object carries the merged
   isosurface and its siblings become geometry-less objects. Only the bundle
   expresses the parent/child link (`SUBELEMENT`); on a classic send the siblings
   are simply properties-only objects in the same collection.
7. **Shared depsgraph handling** — `needs_evaluated_object`,
   `has_cross_object_geometry_deps`, `temporary_mesh` in `to_speckle/utils.py`.

## Receive

### Decision path

`load_operation()` (`connector/operations/load_operation.py`) tries the bundle
first. A bundle-published version **cannot** be loaded any other way: its
`referencedObject` is the synthetic sentinel `binary-{versionId}`, which has no
row in the objects table, so a classic receive 404s on it.

```
load_operation(context, instance_loading_mode)
│
├─ client.version.get(versionId, projectId)
│
├─ _try_load_bundle()
│    is_bundle_receive_available()   pyarrow + specklepy.bundle.sgeo
│                                    + hasattr(sgeo, "decode_mesh"), env not 0
│    │  False -> None (classic)
│    │
│    download_bundle() -> list_artifacts()
│      GET /api/v2/projects/{p}/models/{m}/versions/{v}/artifacts   [bearer]
│      404 / non-2xx / transport error / bad JSON -> []  -> None (classic)
│      keep only *.parquet   (.dat is the viewer's packfile, not the bundle)
│      GET each presigned URL, unauthenticated, follow_redirects, 300 s
│    │  None -> classic
│    │
│    read_bundle(dir)      parquet -> dataclasses          [no bpy]
│    bake_bundle(...)      dataclasses -> bpy.data          [direct bake]
│    report skipped_by_type + decode_errors, redraw outliner
│
├─ bundle result -> _mark_received() -> return
│
└─ classic receive
     operations.receive(version.referenced_object, transport)
     render_material_proxy_to_native -> instance_definition_proxy_to_native
     -> traversal -> convert_to_native per object
```

### Detection

By **probing** the artifacts endpoint and treating "returns files" as the signal
— never by sniffing the `binary-` prefix. The id convention is a producer
detail, and C#'s `ArtifactReceiver` deliberately avoids depending on it too.

`is_bundle_receive_available()` checks for `sgeo.decode_mesh` specifically,
because an older specklepy ships the bundle *encoder* without the decoder; a
plain `import specklepy.bundle` would pass and then crash mid-bake.

### Download

`bundle_receive.py`. Presigned URLs are fetched **without** the bearer token —
the signature is in the URL and some stores reject a second credential. Files
are filtered to `*.parquet`. The whole response body is buffered in memory
before being written, which is [R5](#unresolved-regressions).

### Parsing

`converter/from_bundle/bundle_reader.py` — deliberately **free of `bpy`**, so it
can be exercised against a downloaded bundle directory with no Blender, no
server and no account.

- Tables are matched by **suffix glob** (`*.eav.objects.parquet`), because the
  version-id filename prefix is not known at read time.
- The geometries table is **sharded**: shard 0 is `{base}.geometries.parquet` and
  overflow shards are `{base}.geometries.{N}.parquet`. The reader globs
  `*.geometries*.parquet`; reading only shard 0 silently drops geometry above
  ~1.5 GiB.
- **Three K-spaces** — object K (`eav.objects`), geometry K (`geometries`) and
  node id (`envelope.nodes`, shared by CONTAINER/DEFINITION/INSTANCE/MATERIAL) —
  are independent index spaces, and relations cross them. `DISPLAY` is
  object→geometry while `IN_COLLECTION` is object→node. Resolving an edge against
  the wrong table yields a plausible-looking wrong answer rather than an error,
  so every lookup goes through its own dict.
- Relations resolved: `DISPLAY`, `IN_COLLECTION`, `IN_MODEL`, `IN_SYSTEM`,
  `IN_GROUP`, `DISPLAY_INSTANCE`, `SUBELEMENT`, `DEFINES`, `DEFINES_INSTANCE`,
  `HAS_MATERIAL`. Still ignored from the v5 vocabulary: `HAS_COLOR`, `ON_LEVEL`,
  `IN_ROOM`, `CONNECTS_TO`, `BOUNDS`.
- `CONTAINER` is **polymorphic** — `subtype` (`Collection` | `Model` |
  `MEP System` | `Network` | `Group`) picks the grouping axis, and each axis has
  its own membership relation. `IN_COLLECTION`/`IN_MODEL` are scalar on the
  object; `IN_SYSTEM`/`IN_GROUP` accumulate, because systems and groups overlap
  by design. A missing `subtype` column (pre-polymorphism bundle) reads as
  authored collections, which is what those bundles were.
- Catalog columns read are `envelope.node_kinds(kind, name)` and
  `envelope.rel_types(rel, name)`, matching what specklepy's `EnvelopeWriter`
  emits. The official `bundle-spec.sql` names that column `id` — see
  [R2](#unresolved-regressions).
- eav folding lifts `name` and `speckle_type` onto the object; only paths under
  the `properties.` prefix land in the user-properties dict, and every other
  bare root scalar (`type`, plus whatever another producer writes) goes to the
  internal `root_fields` dict, which the bake never restores as a user custom
  property (was R6). `_eav_value` prefers `value_double`, which is why an int
  published as `42` reads back as `42.0`.
- The root is the parentless `CONTAINER(Collection)` with the lowest node id —
  by subtype and deterministically, never by row order. A cross-producer bundle
  holds several parentless containers at once (each model, system and top-level
  group roots its own axis), so "first parentless row" would crown whichever
  axis the producer happened to write first. `None` when the bundle has no
  authored collections at all, e.g. a bare Navis federation.

### Direct bake

`converter/from_bundle/bundle_to_native.py` takes the **direct-bake** path
(Rhino's `IArtifactHostObjectBuilder`), not the Base-reconstruction path
(Revit's). Parquet arrays go straight to `bpy.data`; no `Base` graph is ever
built, so dense meshes skip per-object pydantic validation entirely. That is why
the raw-array `sgeo.decode_mesh` exists alongside `sgeo.decode`.

Bake order is load-bearing: materials → collections → definitions → objects →
`SUBELEMENT` parenting. Definitions must exist as collections before a placement
can point an empty at one, and every object must exist before subelement
parenting can resolve both ends.

- The published root CONTAINER maps *onto* the caller's root collection rather
  than nesting inside it, so a load does not add a redundant folder level.
- **Container axes map per subtype** (the Outliner contract, pending product
  approval). Blender has one grouping concept, but an object may live in many
  collections at once — which is exactly the spec's multi-axis membership:
  - `Collection` → the authored tree under the root, as always.
  - `Model` → the federation tier. One model maps onto the root like a lone
    authored root does; several become the outermost tier of collections (the
    spec's "outermost scene-view tier when >1 model").
  - `Group` → a `Groups` branch under the root; groups nest via `def_ref` and
    objects link in *additively*, keeping their authored collection.
  - `MEP System` / `Network` → a `Systems` branch, likewise additive.
  - Any other subtype is **not baked**: it is tallied on
    `BakeResult.unmapped_containers` and printed, because an empty folder would
    misread as "this grouping arrived intact". The `Groups`/`Systems` branches
    only exist when their axis does, so a Blender-published bundle gains
    nothing.
  - An object with no resolvable collection sits in its model's tier, else at
    the root.
- **All 11 SGEO primitives decode.** Blender only *publishes* mesh / curve /
  polyline / points, but a Rhino or Revit bundle carries the rest.
- Geometry types map to three data-blocks: `mesh`/`box` → Mesh, the curve family
  → one Curve holding a spline per geometry, `points` → an Empty (single) or a
  vertex-only Mesh (cloud). A Blender object holds one data-block, so an object
  mixing families gets mesh as the primary and the rest as parented children.
  Blender's own publishes are homogeneous; this only fires cross-connector.
- **Parenting participants get their origin recentred onto their geometry**
  (`_recenter_origin`); every other object keeps the identity transform the
  direct-display dialect implies. World-baked data leaves every origin at
  (0, 0, 0), and Blender draws relationship lines origin-to-origin, so before
  this every `SUBELEMENT` link and mixed-family child drew a viewport line from
  the element back to the world origin. The recenter is world-lossless (data
  shifts by −center, the matrix gains +center), skips shared data-blocks, and a
  properties-only parent — an Empty with nothing to recentre onto — moves to
  the component-wise median of its placed children instead, taking its
  identity-local followers with it.
- `HAS_MATERIAL` binds to **geometry, not the object**, hence material *slots*
  and per-face-range assignment rather than one material per object.
- An object whose geometry is *entirely* undecodable is **skipped outright** — no
  placeholder — and the per-type tally is printed. An object with no geometry at
  all (a metaball sibling) becomes an Empty that still carries its properties.
- **Properties are un-flattened before baking.** The eav's dotted paths cannot
  be written verbatim as custom-property keys: IDProperty names are capped at
  63 *bytes* and a Revit parameter path blows through that, which used to abort
  the whole bake (`KeyError` from Blender). `_unflatten_properties` rebuilds the
  paths into nested dicts — baked as IDProperty groups, the shape the classic
  receive produces — so only individual segments face the limit, and an
  over-long segment is fitted on a UTF-8 boundary. The eav separator is a bare
  `.` with no escaping (C# parity), so a key containing a literal dot nests one
  level deeper than authored; the format cannot distinguish the two. A
  scalar/subtree collision on one key keeps the first arrival and tallies the
  loser on `BakeResult.dropped_properties` — one bad property never aborts a
  receive. On republish, `extract_custom_properties` recurses IDProperty groups
  back to plain dicts, which the eav walker re-flattens to the same paths.
- Placements honour `instance_loading_mode`: `INSTANCE_PROXIES` creates a
  collection-instance empty; `LINKED_DUPLICATES` expands the placement into a
  plain empty plus real copies of the members, applied recursively — a nested
  placement is rebuilt as an expanded empty rather than copied, so no
  collection instance survives the mode. `_bake_placement` returns every object
  it creates (primary first, like `_bake_object`) and the caller links them all
  into the target collection, so nothing lands in the scene root (formerly R3).

### Fallback and error behaviour

The intended contract is a deliberate asymmetry:

- **No bundle** (404, no `.parquet` entries, reader force-disabled, old
  specklepy) → return `None` and take the classic path.
- **A bundle that exists but fails to read or bake** → **raise**. Falling back
  would only swap a clear error for a confusing object 404, because the classic
  path provably cannot serve a bundle version.

The probe does not yet implement that contract fully: auth failures, 5xx,
transport errors and malformed JSON are all collapsed into "no bundle" and fall
back. That is [R7](#unresolved-regressions).

## Packaging requirements

**This section is a release blocker, not a note.**

| Dependency | Required | Currently declared | Status |
| --- | --- | --- | --- |
| `specklepy` | a build containing `specklepy.bundle` **and** `sgeo.decode_mesh` | `>=2026.6.0`, locked to `2026.6.0` | **fails** |
| `pyarrow` | `>=17.0.0` | `>=17.0.0`, pinned directly | ok |
| bundle-spec | `SCHEMA_VERSION = 5`, inherited from specklepy's vendored `specklepy.bundle.spec` | not pinned by this repo | needs recording |

The locked runtime cannot publish or receive a bundle:

```
$ uv run --frozen python -c "import specklepy.bundle"
ModuleNotFoundError: No module named 'specklepy.bundle'
```

`2026.6.0` is the latest PyPI release and has no `specklepy.bundle`. The producer
and reader currently exist only in unreleased `2026.6.1.devN` builds. With the
locked dependency, `is_bundle_send_available()` and
`is_bundle_receive_available()` both return false, publishing silently stays on
the classic JSON path, and a bundle-published version falls through to
`operations.receive()` with the `binary-{versionId}` sentinel it cannot resolve.

The committed fixture suite passes only because the local Blender install has a
manually placed `2026.6.1.dev*` in
`~/.config/Speckle/connector_installations/Blender <ver>/`.

Required before release:

1. Pin a released `specklepy` that contains the producer, the reader and
   `sgeo.decode_mesh`; update `pyproject.toml` and relock.
2. Record the `speckle-bundle-spec` commit that specklepy generated its
   `spec/bundle_spec.py` from, so producer, reader and validator are traceable to
   one artifact.
3. Treat runtime feature detection as a safety net for older servers, **not** as
   the mechanism that decides whether the migration is active. A minimum version
   must be enforced by the dependency declaration.

## Validation: what is actually checked

### The local harness

`tools/run_fixture.sh --all` runs the real conversion and bundle export inside
`Blender --background` and decodes the parquet output into assertable text — no
GUI, account or server. 12 fixture scenes; 11 carry assertions and pass;
`duplicate_materials` is report-only (`EXPECT = {}`).

The harness covers the **publish** direction only. There are no receive
assertions.

### The official spec validator

`npm run validate -- <bundle-dir>` in the `speckle-bundle-spec` repo. All 12
emitted fixture bundles return `validate: PASS`.

It checks: required files present, live relation/kind ids, selected table
columns, and dense contiguous object / node / geometry K-spaces.

It does **not** check: catalog table column shapes, EAV value exclusivity
(`bundle-spec.sql:54`, "exactly one of
`value_string`/`value_double`/`value_boolean` is set"), semantic correctness of
relation endpoints, or geometry content. A `validate: PASS` therefore means
"structurally well-formed", not "semantically conformant" — which is why
[R2](#unresolved-regressions) survived a green validator run.

### What still needs coverage

1. A `bpy`-free `bundle_reader` suite driven by parquet tables generated from the
   **official** schemas, not by the same specklepy that the reader pairs with —
   otherwise producer and reader can drift together unnoticed.
2. Receive round-trip fixtures for mesh, curves, materials, properties,
   collection instances, nested instances, subelements, and both instance
   loading modes.
3. Real `sign` / upload / `complete` coverage against a server.
4. Contract tests for artifact-probe status handling and streamed downloads.
5. A `FONT` fixture — the new path calls Blender `to_mesh()`, which
   `fake-bpy-module` cannot exercise.
6. Material-name and geometry-material assertions in `duplicate_materials`.

Per `CLAUDE.md`, the harness stays out of CI by deliberate choice while the
bundle format moves. A deterministic, Blender-free producer conformance fixture
would be the thing to gate in CI instead.

## Known data losses and approximation limits

These are **accepted, documented behaviour changes** — they need release notes
and product acceptance, not code fixes.

Bundle path only:

- **Version messages are dropped.** The v2 `complete` payload has no message
  field (a server-side API gap). Same as the IFC converter. Because of this the
  UI no longer offers a message input at all — the publish buttons act
  immediately, with no dialog. `publish_operation`'s `version_message` parameter
  remains as the reconnection point once the server accepts one.
- **Lists never serialise.** specklepy's eav walker skips list values (C#
  parity), so array-valued custom properties survive only a classic send.
- **Data-block properties do not reach the eav table.** Mesh/curve custom
  properties are dropped by SGEO geometry encoding; only object-level properties
  are queryable. See `merge_data_block_properties()` for the open decision.
- **Integers become floats.** The eav table has no integer column, so `obj["n"]
  = 42` reads back as `42.0`.

Conversion, both paths:

- NURBS **surfaces** are tessellated — SGEO has no Surface primitive.
- **Text** is tessellated to glyph meshes; the string and layout ride along as
  properties.
- **Metaballs** publish per family, not per element. `MetaElement` granularity is
  not represented: elements have no stable identity to key an applicationId on.
  Selecting a member without its basis publishes the whole family, which is the
  only way its geometry exists, and logs that it did.
- Solid curves are tessellated; only genuine wires keep exact splines.

Receive:

- **Blender cannot set a NURBS knot vector from Python.** It derives one from
  `order_u`/`use_cyclic_u`/`use_endpoint_u`, so a non-uniform source curve is
  redrawn on a uniform basis. Control points, degree and weights are exact; the
  traced path can drift (half of a 55-curve model within 0.03%, 50/51 within 5%).
- **Arc / circle / ellipse have no Blender primitive** and are tessellated to
  64-segment polylines. An arc's sweep direction is recovered from its midpoint.
- **Undecodable geometry types are skipped** and the object dropped if that is
  all it had; the per-type tally is printed so a reload after a decoder lands
  brings the shape in.
- A member published **both** standalone and as a definition member comes back
  only inside its definition collection, because `load_operation` skips every
  object listed in a definition.
- `instance_type` in `{VERTS, FACES}` and geometry-nodes instancing are not
  published at all — they exist only in the evaluated depsgraph.

## Unresolved regressions

These are **defects**, tracked separately from the accepted limits above. Detail,
reproductions and suggested fixes are in
[`parquet-bundle-regression-report.md`](parquet-bundle-regression-report.md).

| ID | Severity | Area | Summary |
| --- | --- | --- | --- |
| R1 | Critical | Packaging | Locked `specklepy 2026.6.0` has no bundle API, so the migration is inactive in a production-like install ([Packaging](#packaging-requirements)) |
| R2 | Critical | Interoperability | specklepy's producer emits `rel_types(rel)` / `node_kinds(kind)` and non-exclusive EAV value columns, where `bundle-spec.sql` specifies `id` and exactly-one-value. The Blender reader follows its producer, so both sides stamp `schema_version = 5` while diverging from the spec — undetectable from the version number. Fix belongs upstream in specklepy, with the reader following. |
| R5 | High | Scalability | Artifact downloads buffer each whole parquet file in memory (`response.content`), so a sharded geometry file can need ~1.5 GiB of headroom per download |
| R7 | Medium | Error handling | Non-404 probe failures (auth, 5xx, transport, bad JSON) fall back to a receive path that provably cannot serve a bundle version, surfacing later as an unrelated object 404 |

R3 (linked-duplicate copies escaping to the scene root; nested placements
staying instanced regardless of mode) was resolved on this branch (ENG-9025):
placements return every created object for the caller to link, nested
placements expand recursively under `LINKED_DUPLICATES`, and `EXPECT_RECEIVE`
round-trip assertions in the `collection_instances` and `nested_instances`
fixtures pin both loading modes. The ID stays retired so the report's numbering
holds.

R4 (cross-connector CONTAINER axes, ENG-9026) is resolved: `subtype` is read,
all four membership relations bake to the documented mapping above, and the
root is chosen by subtype. Covered by `tools/test_bundle_reader.py` and
`tools/test_bundle_bake.py`; the id is retired, not renumbered.

## Review and release gate

Do not release the migration until R1 and R2 are closed. Before claiming parity
with the classic path, also require:

1. Passing asserted publish **and** receive round trips for both instance
   loading modes.
2. A receive check against a **real** Revit or Navisworks bundle. The synthetic
   multi-axis tables in `tools/test_bundle_reader.py` / `tools/test_bundle_bake.py`
   pin the Model/System/Network/Group semantics, but only a producer-written
   bundle validates the assumptions baked into them.
3. Streamed artifact download coverage with a measured peak RSS.
4. Explicit **product** acceptance of the
   [known data losses](#known-data-losses-and-approximation-limits) — in
   particular dropped version messages, dropped list properties and
   integers-become-floats, all of which are user-visible.
5. Explicit **engineering** sign-off that the
   [shared conversion changes](#shared-conversion-changes) are acceptable on the
   classic fallback, especially the applicationId scheme change, which is not
   backward compatible with versions published before this branch.
6. Release notes derived from this document.
