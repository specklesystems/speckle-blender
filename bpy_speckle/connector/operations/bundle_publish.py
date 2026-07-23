"""Speckle 4.0 parquet-bundle publish path (v2 data endpoints).

The bundle path replaces the classic ``operations.send`` JSON-object upload with
a locally-written parquet bundle (see ``specklepy.bundle``) uploaded via the
server's v2 data endpoints: sign → presigned PUT per file → complete, where the
``complete`` call itself creates the version. The version id is pre-allocated by
the server at ingestion creation and baked into the bundle filenames, so the
ingestion must exist before conversion starts.

Availability is feature-detected on two axes and the caller falls back to the
classic send when either is missing:
- ``specklepy.bundle`` importable (needs a specklepy build with the bundle
  producer and pyarrow installed);
- the server pre-allocates a ``versionId`` on the ingestion (v2 data endpoints).

``SPECKLE_BLENDER_BUNDLE=0`` force-disables the bundle path.
"""

import os
import tempfile
from typing import Optional

from specklepy.logging.exceptions import SpeckleException

_BUNDLE_ENV_VAR = "SPECKLE_BLENDER_BUNDLE"


def is_bundle_send_available() -> bool:
    """True when the bundle producer is importable and not force-disabled."""
    if os.environ.get(_BUNDLE_ENV_VAR, "").strip().lower() in ("0", "false", "no"):
        return False
    try:
        import specklepy.bundle  # noqa: F401

        return True
    except ImportError:
        return False


def fetch_pre_allocated_version_id(
    account, project_id: str, ingestion_id: str
) -> Optional[str]:
    """Read the ingestion's pre-allocated ``versionId`` (a v2-only field).

    Uses a dedicated GraphQL query for the TOP-LEVEL ``ModelIngestion.versionId``
    rather than the shared model_ingestion resource: the field only exists on
    servers with the v2 data endpoints, and selecting it in the SDK's standard
    ingestion queries would break older servers. Returns None when the server
    does not expose it (the caller then falls back to the classic send).
    """
    import httpx

    url = account.serverInfo.url.rstrip("/") + "/graphql"
    headers = {"Authorization": f"Bearer {account.token}"} if account.token else {}
    query = (
        "query($p:String!,$i:ID!){ project(id:$p){ ingestion(id:$i){ versionId } } }"
    )
    try:
        resp = httpx.post(
            url,
            headers=headers,
            json={
                "query": query,
                "variables": {"p": project_id, "i": ingestion_id},
            },
            timeout=60,
        )
        body = resp.json()
    except Exception:
        return None
    if body.get("errors"):
        # older server without the v2 versionId field
        return None
    ingestion = ((body.get("data") or {}).get("project") or {}).get("ingestion") or {}
    return ingestion.get("versionId")


def publish_bundle(
    account,
    project_id: str,
    ingestion_id: str,
    version_id: str,
    root_collection,
) -> str:
    """Write the bundle to a temp dir and upload it. Returns the version id.

    The v2 ``complete`` call creates the version server-side — no
    ``model_ingestion.complete`` follows this.
    """
    from specklepy.bundle.upload import ArtifactPipeline

    from ...converter.to_speckle.bundle_exporter import BlenderBundleExporter

    with tempfile.TemporaryDirectory(prefix="speckle-bundle-") as bundle_dir:
        exporter = BlenderBundleExporter(bundle_dir, version_id)
        root_id, object_count = exporter.export(root_collection)

        for geo_id, error in exporter.conversion_errors:
            print(f"Skipped geometry '{geo_id}' in bundle: {error}")

        if object_count == 0:
            raise SpeckleException("No objects could be written to the bundle")

        with ArtifactPipeline(
            project_id, ingestion_id, version_id, account, bundle_dir
        ) as pipeline:
            return pipeline.upload_dir(version_id, root_id, object_count)
