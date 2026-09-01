"""Local account credentials and account-level (workspace) queries."""

from typing import Dict, List, Optional, Tuple

from specklepy.api.credentials import Account, get_local_accounts

from ..utils.config_store import get_user_selected_account_id
from .client_cache import api_read, client_cache


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
                acc.userInfo.name,
                acc.serverInfo.url,
                acc.userInfo.email,
            )
        )
    return speckle_accounts


def get_default_account_id() -> Optional[str]:
    """
    retrieves the ID of the default Speckle account
    """
    return next(
        (acc.id for acc in get_local_accounts() if acc.isDefault), "NO_ACCOUNTS"
    )


def get_startup_account_id() -> Optional[str]:
    """
    retrieves the account to pre-select when the UI first needs one:
    the machine-wide last selected account (shared with the other
    connectors via DUI3Config), falling back to the default account
    when nothing was persisted or the account no longer exists
    """
    persisted_id = get_user_selected_account_id()
    if persisted_id and any(acc.id == persisted_id for acc in get_local_accounts()):
        return persisted_id
    return get_default_account_id()


def get_server_url_by_account_id(account_id: str) -> Optional[str]:
    """
    retrieves the server URL for a given account ID
    """
    accounts: List[Account] = get_local_accounts()
    for acc in accounts:
        if acc.id == account_id:
            return acc.serverInfo.url
    return None


@api_read("in get_workspaces", lambda: [("", "")])
def get_workspaces(account_id: str) -> List[Tuple[str, str]]:
    """
    retrieves the workspaces for a given account ID
    """
    client = client_cache.get_client(account_id)

    workspaces_enabled = client.server.get().workspaces.workspaces_enabled
    if not workspaces_enabled:
        return []

    workspaces = client.active_user.get_workspaces().items

    workspace_list = [
        (ws.id, ws.name)
        for ws in workspaces
        if ws.creation_state is None or ws.creation_state.completed
    ]

    active_workspace = client.active_user.get_active_workspace()
    default_workspace_id = (
        active_workspace.id
        if active_workspace
        else (workspaces[0].id if workspaces else None)
    )

    if default_workspace_id:
        return _reorder_tuple(workspace_list, default_workspace_id)
    return workspace_list


@api_read("in get_active_workspace", None)
def get_active_workspace(account_id: str) -> Optional[Dict[str, str]]:
    """
    retrieves the ID of the default workspace for a given account ID
    """
    client = client_cache.get_client(account_id)
    active_workspace = client.active_user.get_active_workspace()
    if active_workspace:
        return {"id": active_workspace.id, "name": active_workspace.name}
    return None


def _reorder_tuple(tuple_list, target_id):
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
