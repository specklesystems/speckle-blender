# Parquet bundle migration (Speckle 4.0, bundle-spec 1.0.0)

This document is the review and release contract for Blender's move to the
parquet bundle schema
([speckle-bundle-spec](https://github.com/specklesystems/speckle-bundle-spec),
`schema_version = "1.0.0"`). It describes what the branch actually implements,
what it deliberately does not, and what must close before release.

The bundle is the **only** publish and receive path. There is no classic
object-graph fallback in either direction:

- **Publish** converts the scene onto specklepy's `BundleBuilder` and hands it
  to `specklepy.bundle.send()`. A server without the /api/v2 data endpoints
  cannot receive a publish from this connector.
- **Receive** downloads the version's artifact bundle and bakes it straight
  into `bpy.data`. A version without a bundle raises; the server-side
  **migration service** rewrites pre-bundle versions into bundles, and the
  connector release is gated on that service being deployed and run (see the
  [release gate](#review-and-release-gate)).
- `specklepy[bundle]` and pyarrow are **hard requirements**, checked when the
  add-on registers. There is no kill switch and no runtime feature detection.

Transport, parsing and send orchestration belong to `specklepy.bundle`; the
connector owns conversion (`converter/to_speckle/`) and the bake
(`converter/from_bundle/`) — the C# `IBundleBuilder` boundary: a connector's
send is exactly its conversion.

## Publish

### Flow

`publish_operation()` (`connector/operations/publish_operation.py`) has one
path:

```
publish_operation(context, objects, apply_modifiers)
│
├─ 1. build_collection_hierarchy()                           [no network]
│     unpack_instances -> unpack_metaballs -> analyze_collection_structure
│     -> convert_to_speckle per object -> Speckle `Collection` tree
│     -> renderMaterialProxies attached to the root
│     returns None (nothing converted) -> abort, nothing touched the server
│
├─ 2. BlenderBundleExporter(BundleBuilder).export(root)      [no network]
│     walk -> objects, properties, geometry, containers, definitions,
│     placements, subelements, materials; parquet written locally
│     zero objects -> raise, nothing touched the server
│
└─ 3. specklepy.bundle.send(account, project, model, builder)  [network]
      model_ingestion.create()            -> ingestion id
      get_reserved_version_id()           -> version id (raises if the server
                                             has no /api/v2 data endpoints)
      builder.build().rename_to(version)  -> files named {versionId}.{table}
      ArtifactPipeline upload             sign -> presigned PUT -> complete
      `complete` CREATES the version; any exception -> fail_with_error teardown
```

Conversion runs entirely before the ingestion exists, so a scene that converts
to nothing never leaves an orphaned in-progress ingestion behind. The version's
`referencedObject` is the SDK bundle reference
`bundle.<projectId>.<modelId>.<versionId>` — set by `send()`, not by the
connector. (Earlier iterations of this branch wrote a connector-specific
`binary-{versionId}` sentinel; that is gone, and the reference now matches what
the C# connectors emit.)

### What the exporter emits

`BlenderBundleExporter` (`converter/to_speckle/bundle_exporter.py`) walks the
converted `Collection` tree and drives specklepy's `BundleBuilder`:

| Blender / Speckle | Bundle |
| --- | --- |
| `BlenderObject` | row in `eav.objects`; properties + `name`/`type`/`units`/`speckle_type` root scalars in `eav.eav` |
| `displayValue` meshes & curves | SGEO blobs in `geometries` + `DISPLAY` edges |
| Blender collections | `CONTAINER` nodes (subtype `Collection`) + `IN_COLLECTION` edges |
| materials | `MATERIAL` nodes + `HAS_MATERIAL` edges (geometry → material) |
| collection instances | `DEFINITION` + `INSTANCE` nodes, `DISPLAY_INSTANCE` / `DEFINES`; a nested member placement additionally emits `DEFINES_INSTANCE` + `DEFINES_MEMBER` + `PLACES` (the builder's shape, matching the C# connectors) |
| metaball families | basis carries the merged blob, siblings become `SUBELEMENT` children |

Blender uses the **direct-display dialect** (same as Rhino): an ordinary object's
`displayValue` is already in world coordinates and links straight to geometry.
Collection instances are the one exception and use the DEFINITION/INSTANCE layer
that the C# connectors use for blocks. The default scene view groups by
`IN_COLLECTION`. See `CLAUDE.md` ("Bundle gotchas") for the per-type rules.

The builder owns interning (`get_or_add_*`), edge emission and the parquet
write; the exporter owns only the walk. Reference implementation:
`RhinoBundleBuilder.cs` in speckle-sharp-connectors, and the boundary contract
in `Sdk/Speckle.Connectors.Common/Builders/IBundleBuilder.cs`.

## Conversion changes relative to `main`

These changes live in `converter/to_speckle/`:

1. **New publishable object types.** `SUPPORTED_OBJECT_TYPES` is now
   `{MESH, CURVE, SURFACE, FONT, EMPTY, META}`. On `main` only `MESH` and
   `CURVE` produced a `BlenderObject`; every other type fell out as `None`.
   - `SURFACE` → tessellated meshes (`surface_to_speckle.py`); SGEO has no
     Surface primitive.
   - `FONT` → tessellated glyph meshes plus the string and layout settings as
     properties (`text_to_speckle.py`).
   - `EMPTY` → the one type that publishes with no geometry at all
     (`empty_to_speckle.py`); it is a transform, a name and its properties.
   - `META` → per *family*, not per object (`metaball_unpacker.py`).
2. **Custom properties** (`extract_custom_properties`). Object-level and
   data-block-level properties are both read; `merge_data_block_properties()`
   in `to_speckle.py` currently returns object-level only — an open decision,
   see its docstring. `extract_custom_properties` skips `applicationId` and
   `speckle_type` — the receive bake writes those onto objects as internal
   bookkeeping, and re-collecting them would mint `properties.applicationId` /
   `properties.speckle_type` on every receive-and-republish cycle (ENG-9027). A
   user property authored under either name is consequently not publishable.
3. **Curves split by shape.** `curve_may_have_volume()` sends bevelled, extruded
   or filled curves as tessellated meshes and keeps genuine wires as exact
   splines.
4. **Geometry applicationIds are keyed on the object, not the data-block**
   (`{objectId}:mat{i}`, `{objectId}:curve{i}`). Required because world-baked
   geometry means two objects sharing a data-block describe *different*
   geometry; the old key made linked duplicates collide. Anything keyed on the
   pre-migration scheme (diffing against old versions, stored selections) will
   not match across the migration.
5. **Instance unpacking** (`instance_unpacker.py`) produces `InstanceProxy` /
   `InstanceDefinitionProxy`, which the exporter translates into builder nodes.
   It also *expands the publish set*: members of an instanced collection
   convert even when the user selected only the placement empty.
6. **Metaball unpacking**: the basis object carries the merged isosurface and
   its siblings become geometry-less objects linked by `SUBELEMENT`.
7. **Shared depsgraph handling** — `needs_evaluated_object`,
   `has_cross_object_geometry_deps`, `temporary_mesh` in `to_speckle/utils.py`.

## Receive

### Flow

`load_operation()` (`connector/operations/load_operation.py`):

```
load_operation(context, instance_loading_mode)
│
├─ client.version.get(versionId, projectId)
│
├─ specklepy.bundle.download.download_bundle()               [network]
│    GET /api/v2/projects/{p}/models/{m}/versions/{v}/artifacts   [bearer]
│    404 / no files -> raise "no artifact bundle yet; it may not have been
│                             migrated"
│    other errors   -> raise (SpeckleException; no fallback exists)
│    filters *.viewer.* artifacts; rejects non-bare file names; streams each
│    presigned URL to disk (unauthenticated — the signature is in the URL)
│
├─ specklepy.bundle.read_bundle(dir) -> Model                 [no bpy]
│    geometry parses lazily from the directory
│
├─ bake_bundle(model, ...)      Model -> bpy.data             [direct bake]
│    report skipped_by_type + decode_errors + unmapped containers +
│    dropped properties, redraw outliner
│
└─ _mark_received() -> return baked objects
```

There is deliberately **no fallback**: a bundle that exists but fails to read
or bake raises, and a missing bundle raises with an "artifact bundle" message
(never a format version number). Both load operators guard `load_operation()`
and turn any exception into `self.report({"ERROR"}, …)` + `{"CANCELLED"}`.

### Parsing — specklepy's `Model`

`specklepy.bundle.bundle_reader.read_bundle` joins the tables;
`specklepy.bundle.model.Model` is the typed read facade the bake consumes
(`ModelObject.geometries/collection/groups/system/children/placements`,
`PropertyView`, `RelationIndex`, `parse_transform`). Facts the bake relies on:

- Tables are matched by **suffix glob** (`*.eav.objects.parquet`); the
  version-id filename prefix is not known at read time.
- The geometries table is **sharded**; the SDK reads the whole
  `*.geometries*.parquet` set.
- **Three K-spaces** — object K (`eav.objects`), geometry K (`geometries`) and
  node id (`envelope.nodes`) — are independent, and relations cross them; the
  SDK resolves every edge against its own space.
- `CONTAINER` is **polymorphic** — `subtype` (`Collection` | `Model` |
  `MEP System` | `Network` | `Group`) picks the grouping axis. `IN_GROUP`
  memberships accumulate. Known SDK narrowing: `IN_SYSTEM` is read as
  single-valued (last edge wins), so an object in several overlapping systems
  keeps only one; restoring the overlap is a specklepy fix, not a connector
  shim.
- The eav's `value_double` wins over `value_string`, which is why an int
  published as `42` reads back as `42.0`.
- specklepy's vendored `spec.SCHEMA_VERSION` is `1.0.0`, matching
  `speckle-bundle-spec` `package.json` (verified 2026-09-01). A missing
  `subtype` column is no longer tolerated — pre-polymorphism bundles are the
  migration service's problem, not the reader's.

### Direct bake

`converter/from_bundle/bundle_to_native.py` takes the **direct-bake** path
(Rhino's `IArtifactHostObjectBuilder`), not the Base-reconstruction path
(Revit's). Parquet arrays go straight to `bpy.data`; no `Base` graph is ever
built, so dense meshes skip per-object pydantic validation entirely. That is why
the raw-array `sgeo.decode_mesh` exists alongside `sgeo.decode`.

Bake order is load-bearing: materials → collections → definitions → objects →
`SUBELEMENT` parenting. Definitions must exist as collections before a placement
can point an empty at one, and every object must exist before subelement
parenting can resolve both ends. Geometry parses lazily from the model's
download directory, so the bake runs before the temp directory is removed.

- The root is the parentless `CONTAINER(Collection)` with the lowest node id —
  by subtype and deterministically, never by row order (a cross-producer bundle
  roots every axis). The published root maps *onto* the caller's root
  collection rather than nesting inside it. Root selection is bake-side logic
  now that the parse belongs to specklepy, covered by `tools/test_bundle_bake.py`.
- **Container axes map per subtype** (the Outliner contract): `Collection` →
  the authored tree; `Model` → the federation tier (one model maps onto the
  root, several become the outermost tier); `Group` → a `Groups` branch;
  `MEP System`/`Network` → a `Systems` branch; memberships are additive. Any
  other subtype is tallied on `BakeResult.unmapped_containers`, never baked as
  an empty folder.
- **All 11 SGEO primitives decode.** Geometry types map to three data-blocks:
  `mesh`/`box` → Mesh, the curve family → one Curve, `points` → an Empty or a
  vertex-only Mesh; an object mixing families gets mesh as the primary and the
  rest as parented children.
- **Parenting participants get their origin recentred onto their geometry**;
  every other object keeps the identity transform the direct-display dialect
  implies. The recenter is world-lossless; a properties-only parent moves to
  the median of its placed children.
- `HAS_MATERIAL` binds to **geometry, not the object**, hence material slots
  and per-face-range assignment. The bake uses the SDK's `effective_material`
  (geometry → object → container fallback), so cross-connector object- and
  container-level materials now apply too.
- An object whose geometry is *entirely* undecodable is **skipped outright** and
  tallied; an object with no geometry at all becomes an Empty that still
  carries its properties.
- **Properties are un-flattened before baking** (`PropertyView` → nested
  IDProperty groups): IDProperty names cap at 63 bytes and a Revit parameter
  path blows through that. Over-long segments are fitted on a UTF-8 boundary; a
  scalar/subtree collision keeps the first arrival and tallies the loser on
  `BakeResult.dropped_properties`.
- Placements honour `instance_loading_mode`: `INSTANCE_PROXIES` creates a
  collection-instance empty; `LINKED_DUPLICATES` expands the placement into
  real copies, recursively.

## Packaging requirements

**This section is a release blocker, not a note.**

| Dependency | Required | Currently declared | Status |
| --- | --- | --- | --- |
| `specklepy` | `specklepy[bundle]` with `send`/`download_bundle`/`read_bundle`/`Model`/`BundleBuilder` | `specklepy[bundle]>=2026.9.0a1` (pre-release) | pin must move to the `2026.9.0` stable before release |
| `pyarrow` | `>=17.0.0` | `>=17.0.0`, pinned directly (the runtime install uses `pip --no-deps` and cannot resolve extras) | ok |
| bundle-spec | `schema_version = "1.0.0"`, inherited from specklepy's vendored `specklepy.bundle.spec` | `1.0.0`, matching `speckle-bundle-spec` | ok |

Registration fails with a clear message when `specklepy.bundle` or pyarrow is
missing (`_require_bundle_support` in `bpy_speckle/__init__.py`). There is no
runtime feature detection to fall back on, by design.

## Validation: what is actually checked

### The local harness

`tools/run_fixture.sh --all` runs the real conversion and bundle export inside
`Blender --background` and decodes the parquet output into assertable text — no
GUI, account or server. The export half drives the same
`BlenderBundleExporter` + `BundleBuilder` the publish path uses (finished with
`builder.build()` instead of `send()`); the receive half
(`EXPECT_RECEIVE`) round-trips the emitted bundle through specklepy's
`read_bundle` + `Model` and the real `bake_bundle`, in both instance loading
modes.

### The synthetic cross-connector suites

The publish harness can only produce Blender-shaped bundles, so cross-connector
shapes are fabricated with pyarrow (rel/kind ids imported from the vendored
spec) and pushed through the real receive surface:

- `tools/test_bundle_reader.py` — asserts on specklepy's `read_bundle` +
  `Model` (no Blender; runs in the repo venv). Encodes the ENG-9025/9026/9027
  regressions: multi-axis memberships, adversarial row order, atomized Revit
  family instances.
- `tools/test_bundle_bake.py` — bakes the same shapes in headless Blender,
  including root-collection selection (a bake-side decision).

### The official spec validator

`npm run validate -- <bundle-dir>` in the `speckle-bundle-spec` repo; all
emitted fixture bundles return `validate: PASS`. It checks structure, not
semantics — a PASS means "structurally well-formed".

Per `CLAUDE.md`, the harness stays out of CI by deliberate choice while the
bundle format moves.

## Known data losses and approximation limits

These are **accepted, documented behaviour changes** — they need release notes
and product acceptance, not code fixes.

Publish:

- **Version messages are dropped.** The `complete` payload has no message field
  (a server-side API gap), so the UI offers no message input.
- **Lists never publish.** specklepy's eav walker skips list values (C#
  parity).
- **Data-block properties do not reach the eav table.** Only object-level
  properties are queryable; see `merge_data_block_properties()` for the open
  decision.
- **Integers become floats.** The eav table has no integer column.
- NURBS **surfaces** and **text** are tessellated; **metaballs** publish per
  family (no `MetaElement` granularity); solid curves are tessellated.

Receive:

- **Blender cannot set a NURBS knot vector from Python**, so a non-uniform
  source curve is redrawn on a uniform basis; control points, degree and
  weights are exact.
- **Arc / circle / ellipse have no Blender primitive** and are tessellated to
  64-segment polylines.
- **Undecodable geometry types are skipped** and tallied.
- A definition-only member's properties row bakes as a shapeless empty at the
  root (pinned in the `collection_instances` fixture).
- `instance_type` in `{VERTS, FACES}` and geometry-nodes instancing are not
  published at all — they exist only in the evaluated depsgraph.
- Overlapping `IN_SYSTEM` memberships collapse to one (SDK narrowing, above).

## Unresolved regressions

| ID | Severity | Area | Summary |
| --- | --- | --- | --- |
| R2 | Critical | Interoperability | specklepy's producer emits `rel_types(rel)` / `node_kinds(kind)` and non-exclusive EAV value columns, where `bundle-spec.sql` specifies `id` and exactly-one-value. Still present in `2026.9.0a1` while spec `1.0.0` keeps `id` — both sides stamp the same `schema_version` while diverging from the spec. Fix belongs upstream in specklepy. |

R5 (whole-file download buffering) and R7 (non-404 probe failures silently
falling back) were **resolved by adopting specklepy's transport**: downloads
stream to disk, and every non-404 failure raises. R1/R3/R4 were resolved
earlier; the IDs stay retired so historical numbering holds.

## Review and release gate

Blockers, in order:

1. **specklepy `2026.9.0` stable published and the pin bumped** off the
   `2026.9.0a1` pre-release.
2. **The server-side migration service deployed and run.** The connector cannot
   load unmigrated versions; this is the explicit gate for removing the classic
   receive.
3. End-to-end against a real server: publish from Blender, load the version
   back, open it in the viewer — confirms the `bundle.<p>.<m>.<v>` root-id
   convention server-side (sharp connectors already emit it).
4. Both synthetic suites green, `tools/run_fixture.sh --all` green, ruff clean.
5. Explicit **product** acceptance of the
   [known data losses](#known-data-losses-and-approximation-limits) — in
   particular dropped version messages, dropped list properties and
   integers-become-floats, all of which are user-visible.
6. Release notes derived from this document.

Out of scope for this branch:
`connector/utils/project_manager.py` keeps a per-project permissions fallback
for old servers — the same species of compatibility, but a different
capability and a separate decision; tracked as a follow-up ticket.
