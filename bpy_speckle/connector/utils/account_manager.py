import bpy
from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account
from specklepy.api.client import SpeckleClient
from .misc import strip_non_ascii


class speckle_account(bpy.types.PropertyGroup):
    id: bpy.props.StringProperty()  # type: ignore
    user_name: bpy.props.StringProperty()  # type: ignore
    server_url: bpy.props.StringProperty()  # type: ignore
    user_email: bpy.props.StringProperty()  # type: ignore


class speckle_workspace(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing workspace information
    """

    id: bpy.props.StringProperty(name="ID")  # type: ignore
    name: bpy.props.StringProperty()  # type: ignore


def get_account_enum_items() -> List[Tuple[str, str, str, str]]:
    accounts: List[Account] = get_local_accounts()
    if not accounts:
        print("No accounts found!")
        return [("NO_ACCOUNTS", "No accounts found!", "", "")]
    print("Accounts added")
    speckle_accounts = []
    for acc in accounts:
        speckle_accounts.append(
            (
                acc.id,
                strip_non_ascii(acc.userInfo.name),
                acc.serverInfo.url,
                acc.userInfo.email,
            )
        )
    return speckle_accounts


def get_workspaces(account_id: str) -> List[Tuple[str, str]]:
    """
    retrieves the workspaces for a given account ID
    """
    account = next((acc for acc in get_local_accounts() if acc.id == account_id), None)
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)
    workspaces_enabled = client.server.get().workspaces.workspaces_enabled

    if workspaces_enabled:
        workspaces = client.active_user.get_workspaces().items
        workspace_list = [
            (ws.id, strip_non_ascii(ws.name))
            for ws in workspaces
            if ws.creation_state == None or ws.creation_state.completed
        ]
        personal_projects_text = "Personal Projects (Legacy)"
    else:
        workspace_list = []
        personal_projects_text = "Personal Projects"
    # Append Personal Projects do workspace dropdown
    if client.active_user.can_create_personal_projects().authorized:
        workspace_list.append(("personal", personal_projects_text))

    print("Workspaces added")
    return (
        reorder_tuple(workspace_list, get_default_workspace_id(account_id))
        if workspaces_enabled
        else workspace_list
    )


def get_default_account_id() -> Optional[str]:
    """
    retrieves the ID of the default Speckle account
    """
    return next(
        (acc.id for acc in get_local_accounts() if acc.isDefault), "NO_ACCOUNTS"
    )


def get_server_url_by_account_id(account_id: str) -> Optional[str]:
    """
    retrieves the server URL for a given account ID
    """
    accounts: List[Account] = get_local_accounts()
    for acc in accounts:
        if acc.id == account_id:
            return acc.serverInfo.url
    return None


def get_default_workspace_id(account_id: str) -> Optional[str]:
    """
    retrieves the ID of the default workspace for a given account ID
    """
    account = next((acc for acc in get_local_accounts() if acc.id == account_id), None)
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)
    return (
        client.active_user.get_active_workspace().id
        if client.active_user.get_active_workspace()
        else "personal"
    )


def get_account_from_id(account_id: str) -> Optional[Account]:
    return next((acc for acc in get_local_accounts() if acc.id == account_id), None)


def reorder_tuple(tuple_list, target_id):
    for i, (id, value) in enumerate(tuple_list):
        if id == target_id:
            # Remove the tuple from its current position
            target_tuple = tuple_list.pop(i)
            # Insert it at the beginning of the list
            tuple_list.insert(0, target_tuple)
            return tuple_list

    # If the target_id wasn't found
    print(f"Tuple with ID {target_id} not found in the list")
    return tuple_list

def can_create_project_in_workspace(account_id: str, workspace_id: str) -> bool:
    """
    Check if the user can create a project in the specified workspace.
    """
    account = get_account_from_id(account_id)
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)

    if workspace_id == "personal":
        return client.active_user.can_create_personal_projects().authorized
    else:
        return client.workspace.get(workspace_id).permissions.can_create_project.authorized