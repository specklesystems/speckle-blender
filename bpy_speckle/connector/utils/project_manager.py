from specklepy.core.api.client import SpeckleClient
from specklepy.core.api.resources.current.workspace_resource import WorkspaceResource
from specklepy.core.api.inputs.project_inputs import WorksaceProjectsFilter
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account
from .misc import format_relative_time, format_role, strip_non_ascii
from .account_manager import _client_cache


def get_projects_for_account(
    account_id: str, workspace_id: str = None, search: Optional[str] = None
) -> List[Tuple[str, str, str, str, bool]]:
    """
    fetches projects for a given account from the Speckle server
    """
    try:
        # Get cached client
        client = _client_cache.get_client(account_id)
        if not client:
            print(f"Error: Could not get client for account: {account_id}")
            return []
        
        # Get account for workspace operations that still need it
        from specklepy.core.api.credentials import get_local_accounts
        account: Optional[Account] = next(
            (acc for acc in get_local_accounts() if acc.id == account_id), None
        )
        if not account:
            print(f"Error: Could not find account with ID: {account_id}")
            return []

        if workspace_id == "personal":
            return _get_personal_projects_with_permissions(client, search)

        try:
            workspace_resource = WorkspaceResource(
                account, client.url, client.httpclient, client.server.version()
            )

            # create filter with search parameter
            filter = (
                WorksaceProjectsFilter(search=search, with_project_role_only=False)
                if search
                else None
            )

            projects_with_permissions = (
                workspace_resource.get_projects_with_permissions(
                    workspace_id=workspace_id, limit=10, filter=filter
                )
            )

            result = []
            for project in projects_with_permissions.items:
                can_load_permission = False

                if hasattr(project, "permissions") and project.permissions:
                    can_load_permission = (
                        hasattr(project.permissions, "can_load")
                        and project.permissions.can_load
                        and project.permissions.can_load.authorized
                    )

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

        except Exception as workspace_error:
            print(
                f"WorkspaceResource failed, falling back to old method: {workspace_error}"
            )
            return _get_projects_with_individual_permissions(
                client, workspace_id, search
            )

    except Exception as e:
        import traceback

        error_msg = f"Error: {str(e)}\n"
        error_msg += f"Traceback:\n{''.join(traceback.format_tb(e.__traceback__))}"
        print(error_msg)
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        return []


def _get_personal_projects_with_permissions(
    client: SpeckleClient, search: Optional[str] = None
) -> List[Tuple[str, str, str, str, bool]]:
    """
    helper function to get personal projects with permissions using the old method
    """
    from specklepy.core.api.inputs.user_inputs import UserProjectsFilter
    from .account_manager import can_load

    filter = UserProjectsFilter(
        search=search,
        workspaceId=None,
        personalOnly=True,
        include_implicit_access=True,
    )

    projects = client.active_user.get_projects(limit=10, filter=filter).items

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


def _get_projects_with_individual_permissions(
    client: SpeckleClient,
    workspace_id: str,
    search: Optional[str] = None,
) -> List[Tuple[str, str, str, str, bool]]:
    """
    Fallback helper function to get projects with permissions using individual API calls
    """
    from specklepy.core.api.inputs.user_inputs import UserProjectsFilter
    from .account_manager import can_load

    filter = UserProjectsFilter(
        search=search,
        workspaceId=workspace_id,
        personalOnly=False,
        include_implicit_access=True,
    )

    projects = client.active_user.get_projects(limit=10, filter=filter).items

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
