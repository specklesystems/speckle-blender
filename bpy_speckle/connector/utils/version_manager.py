from specklepy.core.api.client import SpeckleClient
from specklepy.core.api.credentials import get_local_accounts, Account
from typing import List, Tuple, Optional
from .misc import format_relative_time
from specklepy.core.api.inputs.model_inputs import ModelVersionsFilter
from specklepy.core.api.models.current import Version


def get_versions_for_model(
    account_id: str, project_id: str, model_id: str, search: Optional[str] = None
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

        # Get the account info
        account: Optional[Account] = next(
            (acc for acc in get_local_accounts() if acc.id == account_id), None
        )
        if not account:
            print(f"Error: Could not find account with ID: {account_id}")
            return []

        # Initialize the client
        client: SpeckleClient = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)

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
        return []


def get_latest_version(
    account_id: str, project_id: str, model_id: str
) -> Tuple[str, str, str]:
    try:
        # Validate inputs
        if not account_id or not project_id or not model_id:
            print(
                f"Error: Invalid inputs - account_id: {account_id}, project_id: {project_id}, model_id: {model_id}"
            )
            return ("", "", "")

        # Get the account info
        account: Optional[Account] = next(
            (acc for acc in get_local_accounts() if acc.id == account_id), None
        )
        if not account:
            print(f"Error: Could not find account with ID: {account_id}")
            return ("", "", "")

        # Initialize the client
        client: SpeckleClient = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)

        # Get versions (limit to 1 since we only need the latest)
        versions: List[Version] = client.version.get_versions(
            project_id=project_id, model_id=model_id, limit=1
        ).items

        if not versions:
            print(f"Error: No versions found for model_id: {model_id}")
            return ("", "", "")

        latest = versions[0]
        return (
            latest.id,
            latest.message if latest.message is not None else "No message",
            format_relative_time(latest.created_at),
        )

    except Exception as e:
        print(f"Error fetching latest version: {str(e)}")
        return ("", "", "")
