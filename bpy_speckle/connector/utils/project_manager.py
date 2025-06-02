from specklepy.core.api.client import SpeckleClient
from specklepy.core.api.credentials import get_local_accounts
from specklepy.core.api.inputs.user_inputs import UserProjectsFilter
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account
from .misc import format_relative_time, format_role, strip_non_ascii
from .account_manager import can_load


def get_projects_for_account(
    account_id: str, workspace_id: str = None, search: Optional[str] = None
) -> List[Tuple[str, str, str, str, bool]]:
    """
    fetches projects for a given account from the Speckle server
    """
    try:
        # Get the account info
        accounts: List[Account] = get_local_accounts()
        account: Optional[Account] = next(
            (acc for acc in accounts if acc.id == account_id), None
        )
        if not account:
            return []

        client = SpeckleClient(host=account.serverInfo.url)
        client.authenticate_with_account(account)

        personal_only = workspace_id == "personal"
        workspace_id_query = None if personal_only else workspace_id

        # set include_implicit_access to True to get all projects
        filter = UserProjectsFilter(
            search=search,
            workspaceId=workspace_id_query,
            personalOnly=personal_only,
            include_implicit_access=True,
        )

        projects = client.active_user.get_projects(limit=10, filter=filter).items

        # determine if user can receive from project based on role
        result = []
        for project in projects:
            can_load_permission, _ = can_load(client, project)

            result.append(
                (
                    strip_non_ascii(project.name),
                    format_role(getattr(project, "role", ""))
                    if hasattr(project, "role") and project.role
                    else "",
                    format_relative_time(project.updated_at),
                    project.id,
                    can_load_permission,
                )
            )

        return result

    except Exception as e:
        import traceback

        error_msg = f"Error: {str(e)}\n"
        error_msg += f"Traceback:\n{''.join(traceback.format_tb(e.__traceback__))}"
        print(error_msg)
        return []
