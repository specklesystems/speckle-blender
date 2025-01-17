from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts, Account
from specklepy.core.api.inputs.project_inputs import ProjectModelsFilter
from specklepy.core.api.models.current import Model
from typing import List, Tuple, Optional
from .misc import format_relative_time

def get_models_for_project(account_id: str, project_id: str, search: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """
    Fetch models for a given project from the Speckle server.

    Args:
        account_id: The ID of the Speckle account to fetch models for
        project_id: The ID of the project to fetch models from
        search: Optional search string to filter models

    Returns:
        List of tuples containing (model_name, model_id, last_updated)
        Returns empty list if any error occurs
    """
    try:
        # Validate inputs
        if not account_id or not project_id:
            print(f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}")
            return []

        # Get the account info
        account: Optional[Account] = next((acc for acc in get_local_accounts() if acc.id == account_id), None)
        if not account:
            print(f"Error: Could not find account with ID: {account_id}")
            return []

        # Initialize the client
        client = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)

        # Validate project exists
        try:
            client.project.get(project_id)
        except Exception as e:
            print(f"Error: Project with ID {project_id} not found: {str(e)}")
            return []

        filter = ProjectModelsFilter(search=search) if search else None

        # Get models
        models: List[Model] = client.model.get_models(project_id=project_id, models_limit=10, models_filter=filter).items

        return [(model.name, model.id, format_relative_time(model.createdAt)) for model in models]

    except Exception as e:
        print(f"Error fetching models: {str(e)}")
        return []
