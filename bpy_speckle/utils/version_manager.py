from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts, Account
from typing import List, Tuple, Optional
from .misc import format_relative_time
from specklepy.core.api.inputs.model_inputs import ModelVersionsFilter
from specklepy.core.api.models.current import Version

def get_versions_for_model(account_id: str, project_id: str, model_id: str, search: Optional[str] = None) -> List[Tuple[str, str, str]]:
    """
    Fetch versions for a given model from the Speckle server.

    Args:
        account_id: The ID of the Speckle account to fetch versions for
        project_id: The ID of the project containing the model
        model_id: The ID of the model to fetch versions from
        search: Optional search string to filter versions

    Returns:
        List of tuples containing (version_id, message, last_updated)
        Returns empty list if any error occurs
    """
    try:
        # Validate inputs
        if not account_id or not project_id or not model_id:
            print(f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}, model_id: {model_id}")
            return []

        # Get the account info
        account: Optional[Account] = next((acc for acc in get_local_accounts() if acc.id == account_id), None)
        if not account:
            print(f"Error: Could not find account with ID: {account_id}")
            return []

        # Initialize the client
        client: SpeckleClient = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)

        filter: ModelVersionsFilter = ModelVersionsFilter(search=search, priorityIds=[])

        # Get versions
        versions: List[Version] = client.version.get_versions(project_id=project_id, model_id=model_id, limit=10, filter=filter).items

        return [(version.id, version.message or "No message", format_relative_time(version.createdAt)) for version in versions]

    except Exception as e:
        print(f"Error fetching versions: {str(e)}")
        return []