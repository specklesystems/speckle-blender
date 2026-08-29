from specklepy.api.client import SpeckleClient
from specklepy.api.inputs.project_inputs import WorksaceProjectsFilter
from typing import List, Tuple, Optional
from .misc import format_relative_time, format_role
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

        try:
            # The workspace query requires a non-null workspace id
            # ($workspaceId: String!), so personal projects go through the
            # active_user variant; both return ProjectWithPermissions items.
            if workspace_id:
                filter = (
                    WorksaceProjectsFilter(search=search, with_project_role_only=False)
                    if search
                    else None
                )
                projects_with_permissions = (
                    client.workspace.get_projects_with_permissions(
                        workspace_id=workspace_id, limit=10, filter=filter
                    )
                )
            else:
                from specklepy.api.inputs.user_inputs import UserProjectsFilter

                projects_with_permissions = (
                    client.active_user.get_projects_with_permissions(
                        limit=10,
                        filter=UserProjectsFilter(
                            search=search,
                            personalOnly=False,
                            include_implicit_access=True,
                        ),
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
                        project.name,
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


def _get_projects_with_individual_permissions(
    client: SpeckleClient,
    workspace_id: str,
    search: Optional[str] = None,
) -> List[Tuple[str, str, str, str, bool]]:
    """
    Fallback helper function to get projects with permissions using individual API calls
    """
    from specklepy.api.inputs.user_inputs import UserProjectsFilter
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
                project.name,
                format_role(getattr(project, "role", ""))
                if hasattr(project, "role") and project.role
                else "",
                format_relative_time(project.updated_at),
                project.id,
                can_load_permission,
            )
        )

    return result
