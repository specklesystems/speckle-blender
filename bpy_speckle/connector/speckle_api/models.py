"""Model queries and creation."""

from typing import List, Optional, Tuple

from specklepy.api.inputs import CreateModelInput
from specklepy.api.inputs.project_inputs import ProjectModelsFilter
from specklepy.api.models.current import Model

from ..utils.misc import format_relative_time
from .client_cache import api_read, client_cache


@api_read("fetching models", list)
def get_models_for_project(
    account_id: str, project_id: str, search: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """
    fetches models for a given project from the Speckle server
    """
    if not account_id or not project_id:
        print(
            f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}"
        )
        return []

    # Get cached client
    client = client_cache.get_client(account_id)
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
            model.name,
            model.id,
            format_relative_time(model.updated_at),
        )
        for model in models
    ]


def create_model(account_id: str, project_id: str, model_name: str) -> Tuple[str, str]:
    try:
        # Get cached client
        client = client_cache.get_client(account_id)
        if not client:
            raise ValueError(f"Could not get client for account: {account_id}")

        model = client.model.create(
            input=CreateModelInput(
                name=model_name, description="", project_id=project_id
            )
        )
        return (model.id, model.name)
    except Exception as e:
        # Clear cache on error to prevent stale clients
        client_cache.clear()
        raise e
