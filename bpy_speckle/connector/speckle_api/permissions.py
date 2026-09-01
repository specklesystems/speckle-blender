"""Permission checks: "can this account do X".

These return ``(authorized, message)`` — or a bare bool for the workspace
check — so operators can surface the reason to the user. A failed check is an
answer for the UI, not a broken client, so unlike reads they do not clear the
client cache (except ``can_create_project_in_workspace``, whose outer failure
mode is a client problem).
"""

from typing import Tuple

from .client_cache import api_read, client_cache


def can_load(client, project) -> Tuple[bool, str]:
    try:
        permissions = client.project.get_permissions(project.id)

        if permissions.can_load.authorized:
            return True, ""
        else:
            return (
                False,
                "Your role on this project doesn't give you permission to load.",
            )

    except Exception as e:
        error_msg = f"Failed to check permissions: {str(e)}"
        print(error_msg)
        return False, error_msg


def can_create_version(
    account_id: str, project_id: str, model_id: str
) -> Tuple[bool, str]:
    try:
        client = client_cache.get_client(account_id)
        permissions = client.model.get_permissions(project_id, model_id)

        if permissions.can_create_version.authorized:
            return True, ""
        else:
            message = getattr(permissions.can_create_version, "message", None)
            return (
                False,
                message
                or "Your role on this project doesn't give you permission to publish.",
            )

    except Exception as e:
        error_msg = f"Failed to check permissions: {str(e)}"
        print(error_msg)
        return False, error_msg


def can_create_model(account_id: str, project_id: str) -> Tuple[bool, str]:
    try:
        client = client_cache.get_client(account_id)
        permissions = client.project.get_permissions(project_id)

        if permissions.can_create_model.authorized:
            return True, ""
        else:
            message = getattr(permissions.can_create_model, "message", None)
            return (
                False,
                message
                or "You don't have permission to create models in this project.",
            )

    except Exception as e:
        error_msg = f"Failed to check permissions: {str(e)}"
        print(error_msg)
        return False, error_msg


@api_read("in can_create_project_in_workspace", False)
def can_create_project_in_workspace(account_id: str, workspace_id: str) -> bool:
    """
    Check if the user can create a project in the specified workspace.
    """
    client = client_cache.get_client(account_id)

    try:
        workspace = client.workspace.get(workspace_id)
        return workspace.permissions.can_create_project.authorized
    except Exception as e:
        print(f"Failed to get workspace: {str(e)}")
        return False
