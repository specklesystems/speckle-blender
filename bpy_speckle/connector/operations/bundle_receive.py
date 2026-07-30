"""Speckle 4.0 parquet-bundle receive path (v2 data endpoints).

The mirror of ``bundle_publish.py``. A version published as a bundle has its
``referencedObject`` set to the synthetic sentinel ``binary-{versionId}`` — no
such row exists in the objects table, so the classic ``operations.receive``
404s on it. The real payload is a set of parquet artefacts in blob storage,
served as presigned URLs by::

    GET /api/v2/projects/{projectId}/models/{modelId}/versions/{versionId}/artifacts

Availability is detected by **probing that endpoint**, never by sniffing the
``binary-`` prefix: the id convention is a producer detail, and a receiver that
depends on it breaks the moment a producer changes it. A 404 (or any failure)
means "no bundle here" and the caller falls back to the classic receive.

``SPECKLE_BLENDER_BUNDLE=0`` force-disables this path, matching publish.
"""

from __future__ import annotations

import os
import re
from typing import List, Optional

_BUNDLE_ENV_VAR = "SPECKLE_BLENDER_BUNDLE"
_TIMEOUT_SECONDS = 300.0

# An artefact name becomes a path component under the download directory, so it
# has to be inert: ``os.path.join`` discards the directory entirely for an
# absolute name and ``../`` walks out of it, either of which would let a server
# put bytes anywhere the Blender process can write. Matching a flat file name
# rather than stripping one keeps a producer-side rename loud — the reader globs
# this directory flat, so a nested name would silently drop a whole table.
_FLAT_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.parquet$")


def is_bundle_receive_available() -> bool:
    """True when the bundle reader is importable and not force-disabled."""
    if os.environ.get(_BUNDLE_ENV_VAR, "").strip().lower() in ("0", "false", "no"):
        return False
    try:
        import pyarrow  # noqa: F401
        from specklepy.bundle import sgeo

        # an older specklepy has the encoder but no decoder
        return hasattr(sgeo, "decode_mesh")
    except ImportError:
        return False


def list_artifacts(
    account, project_id: str, model_id: str, version_id: str
) -> List[dict]:
    """Ask the server for this version's artefact bundle.

    Returns ``[{name, url, expiresAt}, …]``, or ``[]`` when the version has no
    bundle or the server predates the v2 data endpoints.
    """
    import httpx

    url = (
        account.serverInfo.url.rstrip("/")
        + f"/api/v2/projects/{project_id}/models/{model_id}"
        + f"/versions/{version_id}/artifacts"
    )
    headers = {"Authorization": f"Bearer {account.token}"} if account.token else {}
    try:
        response = httpx.get(url, headers=headers, timeout=60.0)
    except Exception as e:
        print(f"[Speckle] Artefact probe failed ({e}); using the classic receive.")
        return []

    if response.status_code == 404:
        return []
    if not response.is_success:
        print(
            f"[Speckle] Artefact probe returned {response.status_code}; "
            "using the classic receive."
        )
        return []

    try:
        return response.json().get("files", []) or []
    except Exception:
        return []


def download_bundle(
    account,
    project_id: str,
    model_id: str,
    version_id: str,
    target_dir: str,
) -> Optional[str]:
    """Download a version's artefact bundle into ``target_dir``.

    Returns the directory when a bundle was fetched, or ``None`` when the version
    has none (so the caller falls back). Presigned URLs are unauthenticated —
    the signature is in the URL — so they are fetched without the token.

    Raises ``ValueError`` before writing anything when the server names a file
    that is not a flat ``.parquet`` name.
    """
    import httpx

    files = list_artifacts(account, project_id, model_id, version_id)
    if not files:
        return None

    # .dat is the viewer's own packfile, not part of the parquet bundle
    wanted = [f for f in files if f.get("name", "").endswith(".parquet")]
    if not wanted:
        return None

    for entry in wanted:
        name = entry.get("name", "")
        if not _FLAT_ARTIFACT_NAME.match(name):
            raise ValueError(
                f"Refusing to download artefact {name!r}: a bundle file name must "
                "be a flat file name, not a path."
            )

    os.makedirs(target_dir, exist_ok=True)
    with httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for entry in wanted:
            name, url = entry.get("name"), entry.get("url")
            if not name or not url:
                continue
            response = client.get(url)
            response.raise_for_status()
            with open(os.path.join(target_dir, name), "wb") as f:
                f.write(response.content)

    print(f"[Speckle] Downloaded {len(wanted)} artefact files for version {version_id}")
    return target_dir
