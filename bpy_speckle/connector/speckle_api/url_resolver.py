"""Turning a URL pasted into the project search box into a selection.

Split in two on purpose: parse_speckle_url() is pure string work and decides
whether a search-box entry is a URL at all, so the dialog can reject
unsupported shapes and wrong-server URLs before paying for any network
round-trip; resolve_speckle_url() then fetches the entities the URL points at
using the already-selected account's client.
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..utils.misc import format_relative_time, format_role


class UnsupportedUrlError(ValueError):
    """A URL whose shape the connector cannot turn into a selection.

    The message is shown verbatim in the project selection dialog.
    """


# FE2 paths: /projects/{id}[/models/{modelId}[@{versionId}]]
_PROJECT_PATH_RE = re.compile(
    r"/projects/(?P<project_id>[^/]+)(?:/models/(?P<models>[^/]+))?"
)

# Object ids are 32-char hashes; model and version ids are 10-char.
_OBJECT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class ParsedSpeckleUrl:
    host: str
    origin: str
    project_id: str
    model_id: Optional[str] = None
    version_id: Optional[str] = None


@dataclass
class ResolvedSpeckleUrl:
    project_id: str
    project_name: str
    role: str
    updated: str
    can_receive: bool
    model_id: str = ""
    model_name: str = ""
    version_id: str = ""
    load_option: str = ""


def _normalized_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def parse_speckle_url(text: str) -> Optional[ParsedSpeckleUrl]:
    """Parse a search-box entry as a Speckle project URL.

    Returns None when the text is not a URL at all — the caller treats it as
    a plain search term. Raises UnsupportedUrlError for URLs the connector
    cannot select from.
    """
    text = text.strip()
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    match = _PROJECT_PATH_RE.search(parsed.path)
    if not match:
        raise UnsupportedUrlError("Not a Speckle project URL")

    model_id = version_id = None
    models = match.group("models")
    if models:
        if "," in models:
            raise UnsupportedUrlError("Multi-model URLs are not supported")
        if models.startswith("$"):
            raise UnsupportedUrlError("Saved view URLs are not supported")
        if models == "all":
            raise UnsupportedUrlError("'All models' URLs are not supported")
        model_id, _, version_id = models.partition("@")
        if _OBJECT_ID_RE.match(model_id):
            raise UnsupportedUrlError("Object URLs are not supported")

    return ParsedSpeckleUrl(
        host=parsed.netloc,
        origin=_normalized_origin(text),
        project_id=match.group("project_id"),
        model_id=model_id or None,
        version_id=version_id or None,
    )


def is_same_server(server_url: str, parsed: ParsedSpeckleUrl) -> bool:
    return _normalized_origin(server_url) == parsed.origin


def resolve_speckle_url(
    account_id: str, parsed: ParsedSpeckleUrl, resolve_version: bool
) -> Tuple[Optional[ResolvedSpeckleUrl], str]:
    """Fetch the entities a parsed URL points at. Returns (resolved, error).

    resolve_version=False (publish mode) skips version lookups entirely —
    a version is meaningless for a publish target.
    """
    from .client_cache import client_cache

    client = client_cache.get_client(account_id)

    try:
        project = client.project.get(parsed.project_id)
    except Exception:
        return None, "Project not found, or you don't have access to it"

    try:
        can_receive = client.project.get_permissions(project.id).can_load.authorized
    except Exception:
        can_receive = False

    resolved = ResolvedSpeckleUrl(
        project_id=project.id,
        project_name=project.name,
        role=format_role(project.role) if getattr(project, "role", None) else "",
        updated=format_relative_time(project.updated_at),
        can_receive=can_receive,
    )

    if parsed.model_id:
        try:
            model = client.model.get(parsed.model_id, project.id)
        except Exception:
            return None, "Model not found in this project"
        resolved.model_id = model.id
        resolved.model_name = model.name

        if resolve_version:
            if parsed.version_id:
                try:
                    version = client.version.get(parsed.version_id, project.id)
                except Exception:
                    return None, "Version not found in this project"
                resolved.version_id = version.id
                resolved.load_option = "SPECIFIC"
            else:
                try:
                    versions = client.version.get_versions(
                        project_id=project.id, model_id=model.id, limit=1
                    ).items
                except Exception:
                    versions = []
                resolved.version_id = versions[0].id if versions else ""
                resolved.load_option = "LATEST"

    return resolved, ""
