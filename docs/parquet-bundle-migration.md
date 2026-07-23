# Parquet bundle (Speckle 4.0) publish path

This branch migrates the publish flow to the new parquet-based bundle schema
([speckle-bundle-spec](https://github.com/specklesystems/speckle-bundle-spec),
schema v5), following the pattern of the IFC converter and the C# connectors.

## How it works

The classic path serialized a nested `Base` tree to detached JSON objects via
`operations.send` + `ServerTransport`, then minted a version through
`model_ingestion.complete` (or `version.create`). The bundle path instead:

1. Creates the model ingestion **before** converting (the server pre-allocates
   the `versionId` at ingestion creation, and the bundle filenames are keyed by
   it).
2. Reuses the existing conversion pipeline unchanged
   (`build_collection_hierarchy` → `Collection` tree of `BlenderObject`s with
   world-coordinate `displayValue` meshes/curves + `renderMaterialProxies`).
3. `BlenderBundleExporter` (`converter/to_speckle/bundle_exporter.py`) walks
   that tree and drives specklepy's `ObjectsArtifactPipeline`, writing the
   parquet bundle to a temp dir:
   - objects → `eav.objects` / properties flattened into `eav.eav`
   - display meshes & curves → SGEO blobs in `geometries` + `DISPLAY` edges
   - Blender collections → `CONTAINER` nodes (subtype `Collection`) +
     `IN_COLLECTION` edges; default scene view groups by `IN_COLLECTION`
   - materials → `MATERIAL` nodes + `HAS_MATERIAL` edges (geometry → material)
4. `ArtifactPipeline` uploads via the v2 data endpoints (`sign` → presigned S3
   `PUT` per file → `complete`); the `complete` call creates the version.

## Fallback behaviour

The bundle path activates only when **both** hold, otherwise the classic send
runs unchanged:

- `specklepy.bundle` is importable (a specklepy build containing the bundle
  producer, plus `pyarrow`);
- the server pre-allocates a `versionId` on the ingestion (v2 data endpoints).

Set `SPECKLE_BLENDER_BUNDLE=0` to force-disable the bundle path.

## Current constraints

- **specklepy release**: the bundle producer is merged on specklepy `main`
  (PR #502) but not yet in a PyPI release (latest: 2026.6.0). Until it ships,
  the runtime feature-detection keeps the connector on the classic path. To
  test now, install specklepy from source into the connector installation
  path (`~/.config/Speckle/connector_installations/<Blender x.y>/`):
  `pip install -t <path> --no-deps /path/to/specklepy`.
- **Version message**: the v2 `complete` payload has no message field yet, so
  the version message is dropped on the bundle path (same as the IFC
  converter).
- **Receive** still uses the classic `operations.receive` path.

## Validation

The exporter output passes the official spec validator
(`speckle-bundle-spec`: `npm run validate -- <bundle-dir>`): all required
tables, live rel/kind ids, and dense contiguous K-spaces.
