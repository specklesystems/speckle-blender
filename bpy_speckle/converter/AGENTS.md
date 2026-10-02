# bpy_speckle/converter

Area guidance for the publish (`to_speckle/`) and receive (`from_bundle/`) converters. The root
`AGENTS.md` holds the two pipelines' shape and the harness policy; this file holds what bites when
you touch the bundle itself. Cross-connector shapes (models, systems, groups, adversarial row order)
are tested by `tools/test_bundle_reader.py` (no Blender) and `tools/test_bundle_bake.py` (headless
Blender) — the publish harness cannot produce them.

## Receive pipeline

Three stages; the first two belong to specklepy:

- `specklepy.bundle.download.download_bundle` — `GET …/versions/{v}/artifacts`, then streams each
  presigned file (it filters `*.viewer.*` artifacts and rejects non-bare file names).
- `specklepy.bundle.bundle_reader.read_bundle` + `specklepy.bundle.model.Model` — parquet → the
  typed read facade the bake consumes. Geometry parses lazily from the download directory, so the
  bake must run before the tempdir goes.
- `from_bundle/bundle_to_native.py` — the stable public Blender seam: a short
  `bake_bundle(model, …)` coordinator plus the `BakeResult` export. It visibly orders materials,
  containers, definition collections, ordinary objects and placements, membership, properties, and
  final hierarchy restoration.

Blender construction lives behind the private `from_bundle/_baking/` package. `GeometryBuilder` is
the sole geometry interface used by orchestration and definition construction; its `mesh` and
`curves` modules own the SGEO-family details. Sibling modules own materials, containers and
membership, properties, instances, transforms, hierarchy repair, and the bake result. Dependencies
point inward from the coordinator and never back to `bundle_to_native` or `load_operation`.

## Receive gotchas

- **Three K-spaces, and relations cross them.** `object K` (a row in `eav.objects`), `geometry K`
  (a row in `geometries`) and `node id` (a row in `envelope.nodes`, shared by
  CONTAINER/DEFINITION/INSTANCE/MATERIAL) are independent index spaces. `DISPLAY` is
  object→geometry but `IN_COLLECTION` is object→node; resolving an edge against the wrong table
  yields a plausible-looking wrong answer rather than an error, so every lookup goes through its
  own dict.
- **`HAS_MATERIAL` binds to geometry, not to the object.** One object's two display meshes can
  carry different materials, hence material *slots* and per-face-range assignment rather than one
  material per object.
- **All 11 SGEO primitives decode.** Blender only *publishes* mesh / curve / polyline / points, but
  a Rhino or Revit bundle carries the rest, so the whole family is handled. `sgeo.decode_mesh` is a
  raw-array fast path for MESH only — meshes are the dense case; curves go through `sgeo.decode`
  to a `Base` because the object model carries the NURBS definition needed to rebuild a spline. An
  object whose geometry is *entirely* undecodable is **skipped outright** — no placeholder — and
  the per-type tally is printed.
- **Geometry types map to three Blender data-blocks**: `mesh`/`box` → Mesh, the curve family → one
  Curve holding a spline per geometry, `points` → an Empty (single) or a vertex-only Mesh (cloud).
  A Blender object holds one data-block, so an object mixing families gets mesh as the primary and
  the rest as parented children. Blender's own publishes are always homogeneous; this only fires
  cross-connector.
- **Blender cannot set a NURBS knot vector from Python.** It derives one from
  `order_u`/`use_cyclic_u`/`use_endpoint_u`, so a non-uniform source curve is redrawn on a uniform
  basis — control points, degree and weights are exact, the traced path can drift (half of a
  55-curve model within 0.03%, 50/51 within 5%). Arc/circle/ellipse have no Blender primitive at
  all and are tessellated to polylines; an arc's sweep direction comes from its midpoint, since
  three points alone don't say which way round.
- **Do not trust `Curve.periodic` for `use_endpoint_u`.** The publish side writes
  `periodic = not spline.use_endpoint_u`, but Bezier splines have no meaningful `use_endpoint_u`, so
  every Bezier arrives claiming to be periodic and comes back visibly short of its endpoints.
  `_is_clamped()` reads the knot vector instead and only falls back to the flag when the knots say
  nothing.
- **Only the translation is unit-scaled** in a placement matrix. Scaling all 16 doubles would scale
  the basis vectors too and resize the instance — invisible in metres, obvious in millimetres.
- **The geometries table is sharded.** Shard 0 is `{base}.geometries.parquet`, overflow shards are
  `{base}.geometries.{N}.parquet`. specklepy's `read_geometries` globs the whole set; reading only
  shard 0 would silently drop geometry above ~1.5 GiB. (`tools/inspect_bundle.py` reads shard 0
  only — fine for fixtures, wrong for a real model.)
- The published root CONTAINER maps *onto* the caller's root collection rather than nesting inside
  it, so a load does not add a redundant folder level.
- **CONTAINER is polymorphic and each subtype is its own grouping axis.** `subtype`
  (`Collection` | `Model` | `MEP System` | `Network` | `Group`) discriminates; membership comes via
  `IN_COLLECTION`/`IN_MODEL` (scalar) and `IN_SYSTEM`/`IN_GROUP` (overlapping by design — but note
  specklepy currently reads `IN_SYSTEM` as single-valued, last edge wins; only groups accumulate.
  Restoring the system overlap is a specklepy fix, not a connector shim). The root is the
  parentless `CONTAINER(Collection)` with the lowest node id, **never** "first parentless row": a
  cross-producer bundle roots every axis, so row order would crown a random model or system. The
  bake maps models to the outermost tier (>1) or onto the root (1), and parks groups/systems under
  `Groups`/`Systems` branches that objects multi-link into; unknown subtypes are tallied, not baked
  as empty folders.

## Bundle (publish) gotchas

- Blender uses the **direct-display dialect** (same as Rhino): an ordinary object's `displayValue`
  is already in world coordinates, so it links straight to geometry with a `DISPLAY` edge.
- **Geometry ids are keyed on the object, never the data-block.** World-baked geometry needs an
  object-scoped identity, or linked duplicates collide and the exporter's id-keyed cache serves them
  all the first copy's mesh. See `get_submesh_id` / `get_curve_element_id`.
- **Collection instances are the one exception to direct-display**, and use the same
  DEFINITION/INSTANCE layer as the C# connectors' blocks: `instance_unpacker.py` turns a placement
  empty into an `InstanceProxy` + `InstanceDefinitionProxy` (Rhino's `RhinoInstanceUnpacker`), and
  `bundle_exporter.py` translates those to builder nodes (Rhino's `RhinoBundleBuilder`). The proxy
  layer keeps the unpacker free of bundle vocabulary — same split as the C# connectors.
  - The placement transform is `empty.matrix_world @ Translation(-collection.instance_offset)` —
    members bake their own `matrix_world` as definition-local geometry, so the collection pivot has
    to come back out of the placement.
  - **Definition members are usually real scene objects too**, unlike a Rhino block's members. A
    member is suppressed from the scene tree (no `IN_COLLECTION`, no `DISPLAY`) only when the user
    did *not* select it in its own right; the unpacker says which via the root's
    `definitionOnlyObjects`.
  - A collection holding *only* definition-only members emits no `CONTAINER` node — otherwise the
    usual excluded-from-the-view-layer "library" collection leaves an empty folder in the viewer's
    scene tree.
  - Known wart: a definition-only member's properties row has no `DISPLAY` edge, so the bake's
    properties-only path (meant for metaball siblings) gives it a shapeless empty at the root —
    pinned in the `collection_instances` fixture so a change to it is loud.
  - Not yet handled: `instance_type` in `{VERTS, FACES}` and geometry-nodes instancing, which only
    exist in the evaluated depsgraph.
- **Metaballs publish per family, not per object**, and are the only type using the `SUBELEMENT`
  edge. Blender sums the fields of every metaball sharing a base name (`Mball`, `Mball.001`) and
  polygonizes one merged isosurface onto the **basis** — the lowest numeric suffix, where an
  unsuffixed name sorts lowest. The basis becomes the family object carrying the blob; its siblings
  become properties-only SUBELEMENT children, keeping their own `IN_COLLECTION` edge.
  `metaball_unpacker.py` assigns the roles, `bundle_exporter._emit_subelements` emits the edges.
  - This ports Revit's curtain wall (`ElementUnpacker` + `RevitArtifactRootObjectBuilder.EmitChild`)
    **inverted**: there the parent is an empty container and the children own the geometry; here
    the basis owns all of it and the children own none. A metaball's isosurface is continuous
    across contributors, so per-member geometry does not exist even in principle.
  - A non-basis member evaluates to an *empty mesh*, not an error, and only the basis is worth
    tessellating. Hidden members contribute no field at all.
  - The merged mesh is in **basis-local** space with siblings baked in, so
    `mesh_to_speckle_meshes(basis, …)` recovers world coordinates. A non-uniformly scaled basis
    genuinely deforms the blob, matching the viewport.
  - Selecting a member without its basis publishes the *whole* family (the only way geometry
    exists) and logs that it did. Not yet handled: `MetaElement` granularity — elements have no
    stable identity to key an applicationId on.
- **Only object-level properties reach the eav table.** Data-block (mesh/curve) custom properties
  are dropped by SGEO geometry encoding. There is an open decision in
  `merge_data_block_properties()` in `to_speckle/to_speckle.py` about whether that should change;
  the current default is object-only.
- **Lists never publish.** specklepy's eav walker skips list values (C# parity), so array-valued
  custom properties are dropped.
- **Collection parentage is not a relation.** A `CONTAINER` node's `def_ref` points at its parent,
  so nesting N collections still yields one `IN_COLLECTION` edge per *object*. Assert placement,
  not edge counts.
- **Integers become floats.** The eav table populates `value_double`, so `obj["n"] = 42` reads back
  as `42.0`.
- Curves split by shape: `curve_may_have_volume()` sends solids as tessellated meshes and keeps
  genuine wires as exact splines.
- Validate exporter output against the official validator when the format changes:
  `npm run validate -- <dir>` in the `speckle-bundle-spec` repo.
