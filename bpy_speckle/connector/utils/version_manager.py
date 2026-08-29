from specklepy.api.client import SpeckleClient
from .account_manager import _client_cache
from typing import List, Optional, Tuple
from .misc import format_relative_time
from specklepy.api.inputs.model_inputs import ModelVersionsFilter
from specklepy.api.models.current import Version


def get_versions_for_model(
    account_id: str, project_id: str, model_id: str
) -> List[Tuple[str, str, str]]:
    """
    fetches versions for a given model from the Speckle server
    """
    try:
        # Validate inputs
        if not account_id or not project_id or not model_id:
            print(
                f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}, model_id: {model_id}"
            )
            return []

        # Get cached client
        client: SpeckleClient = _client_cache.get_client(account_id)
        if not client:
            print(f"Error: Could not get client for account: {account_id}")
            return []

        filter: ModelVersionsFilter = ModelVersionsFilter(priorityIds=[])

        # Get versions
        versions: List[Version] = client.version.get_versions(
            project_id=project_id, model_id=model_id, limit=10, filter=filter
        )
        versions_list: List[Tuple[str, str, str]] = []
        for version in versions.items:
            if version.referenced_object != "":
                versions_list.append(
                    (
                        version.id,
                        version.message
                        if version.message is not None
                        else "No message",
                        format_relative_time(version.created_at),
                    )
                )
        return versions_list

    except Exception as e:
        print(f"Error fetching versions: {str(e)}")
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        return []


def get_latest_version(
    account_id: str, project_id: str, model_id: str
) -> Optional[Tuple[str, str, str]]:
    """Return (id, message, relative time) for a model's latest version.

    Returns `None` — never a tuple of empty strings — when there is no latest
    version to report, so that callers can test the result directly. A tuple is
    always truthy, so an in-band empty sentinel silently turns every
    `if latest_version:` guard into dead code.
    """
    try:
        # Validate inputs
        if not account_id or not project_id or not model_id:
            print(
                f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}, model_id: {model_id}"
            )
            return None

        # Get cached client
        client: SpeckleClient = _client_cache.get_client(account_id)
        if not client:
            print(f"Error: Could not get client for account: {account_id}")
            return None

        # Get versions (limit to 1 since we only need the latest)
        versions: List[Version] = client.version.get_versions(
            project_id=project_id, model_id=model_id, limit=1
        ).items

        if not versions:
            print(f"Error: No versions found for model_id: {model_id}")
            return None

        latest = versions[0]
        return (
            latest.id,
            latest.message if latest.message is not None else "No message",
            format_relative_time(latest.created_at),
        )

    except Exception as e:
        print(f"Error fetching latest version: {str(e)}")
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        return None
