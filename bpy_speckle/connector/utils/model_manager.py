from specklepy.core.api.inputs.project_inputs import ProjectModelsFilter
from specklepy.core.api.models.current import Model
from typing import List, Tuple, Optional
from .misc import format_relative_time, strip_non_ascii
from .account_manager import _client_cache


def get_models_for_project(
    account_id: str, project_id: str, search: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """
    fetches models for a given project from the Speckle server
    """
    try:
        if not account_id or not project_id:
            print(
                f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}"
            )
            return []

        # Get cached client
        client = _client_cache.get_client(account_id)
        if not client:
            print(f"Error: Could not get client for account: {account_id}")
            return []

        try:
            client.project.get(project_id)
        except Exception as e:
            print(f"Error: Project with ID {project_id} not found: {str(e)}")
            return []

        filter = ProjectModelsFilter(search=search) if search else None

        models: List[Model] = client.model.get_models(
            project_id=project_id, models_limit=10, models_filter=filter
        ).items

        return [
            (
                strip_non_ascii(model.name),
                model.id,
                format_relative_time(model.updated_at),
            )
            for model in models
        ]

    except Exception as e:
        print(f"Error fetching models: {str(e)}")
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        return []
