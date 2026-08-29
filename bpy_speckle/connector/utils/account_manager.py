import bpy
from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional, Dict
from urllib.parse import urlparse
from specklepy.api.credentials import Account
from specklepy.api.client import SpeckleClient
from .config_store import get_user_selected_account_id


class SpeckleClientCache:
    def __init__(self):
        self._clients: Dict[str, SpeckleClient] = {}

    def get_client(self, account_id: str) -> SpeckleClient:
        # Check cache first
        if account_id in self._clients:
            print(f"[Cache HIT] Using cached client for account {account_id}")
            return self._clients[account_id]

        # Create new client if needed
        print(f"[Cache MISS] Creating new client for account {account_id}")
        account = get_account_from_id(account_id)
        if not account:
            raise ValueError(f"No account found for ID: {account_id}")

        url = account.serverInfo.url
        use_ssl = urlparse(url).scheme.lower() != "http"
        client = SpeckleClient(host=url, use_ssl=use_ssl)
        client.authenticate_with_account(account)
        self._clients[account_id] = client
        return client

    def clear(self) -> None:
        """Clear all cached clients."""
        print("[Cache] Clearing all cached clients")
        self._clients.clear()


# Global cache instance
_client_cache = SpeckleClientCache()


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
                acc.userInfo.name,
                acc.serverInfo.url,
                acc.userInfo.email,
            )
        )
    return speckle_accounts


def get_workspaces(account_id: str) -> List[Tuple[str, str]]:
    """
    retrieves the workspaces for a given account ID
    """

    try:
        # Get client from cache
        client = _client_cache.get_client(account_id)

        workspaces_enabled = client.server.get().workspaces.workspaces_enabled

        if workspaces_enabled:
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
                result = reorder_tuple(workspace_list, default_workspace_id)
            else:
                result = workspace_list
        else:
            result = []

        return result
    except Exception as e:
        print(f"Error in get_workspaces: {str(e)}")
        _client_cache.clear()  # Clear cache on error
        return [("", "")]


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


def get_active_workspace(account_id: str) -> Optional[Dict[str, str]]:
    """
    retrieves the ID of the default workspace for a given account ID
    """
    try:
        client = _client_cache.get_client(account_id)
        active_workspace = client.active_user.get_active_workspace()
        if active_workspace:
            return {"id": active_workspace.id, "name": active_workspace.name}
        return None
    except Exception as e:
        print(f"Error in get_active_workspace: {str(e)}")
        _client_cache.clear()
        return None


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
        client = _client_cache.get_client(account_id)
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
        client = _client_cache.get_client(account_id)
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


def can_create_project_in_workspace(account_id: str, workspace_id: str) -> bool:
    """
    Check if the user can create a project in the specified workspace.
    """
    try:
        client = _client_cache.get_client(account_id)

        try:
            workspace = client.workspace.get(workspace_id)
            return workspace.permissions.can_create_project.authorized
        except Exception as e:
            print(f"Failed to get workspace: {str(e)}")
            return False
    except Exception as e:
        print(f"Error in can_create_project_in_workspace: {str(e)}")
        _client_cache.clear()  # Clear cache on error
        return False
