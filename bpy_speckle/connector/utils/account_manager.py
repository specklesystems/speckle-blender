import bpy
from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account
from specklepy.api.client import SpeckleClient
from specklepy.api.wrapper import StreamWrapper

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
    if not account:
        print("No accounts found > No workspaces!")
        return [("", "")]
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)
    workspaces_enabled = client.server.get().workspaces.workspaces_enabled

    if workspaces_enabled:
        workspaces = client.active_user.get_workspaces().items
        workspace_list = [
            (ws.id, strip_non_ascii(ws.name))
            for ws in workspaces
            if ws.creation_state is None or ws.creation_state.completed
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


def get_project_from_url(
    url: str,
) -> Tuple[Optional[StreamWrapper], Optional[object], Optional[object], str]:
    """
    get a project from a URL, handling all the client setup.
    """
    try:
        wrapper = StreamWrapper(url)
        client = wrapper.get_client()
        client.authenticate_with_account(wrapper.get_account())

        # get the stream_id (project_id) from the wrapper
        if not wrapper.stream_id:
            return wrapper, client, None, "Could not extract project ID from URL"

        project = client.project.get(wrapper.stream_id)

        if not project:
            return wrapper, client, None, "Could not access project"

        return wrapper, client, project, ""

    except Exception as e:
        return None, None, None, f"Failed to process URL: {str(e)}"


def get_model_details_by_wrapper(
    wrapper: StreamWrapper,
) -> Tuple[str, str, str, str, str, str, str]:
    """
    extract model details from a StreamWrapper object.
    """
    client = wrapper.get_client()
    client.authenticate_with_account(wrapper.get_account())
    (
        account_id,
        project_id,
        project_name,
        model_id,
        model_name,
        version_id,
        load_option,
    ) = "", "", "", "", "", "", ""
    account_id = wrapper.get_account().id
    if wrapper.stream_id:
        project_id = wrapper.stream_id
        project_name = client.project.get(project_id).name
    if wrapper.model_id:
        model_id = wrapper.model_id
        model = client.model.get(model_id, project_id)
        model_name = model.name
        load_option = "LATEST" if not wrapper.commit_id else "SPECIFIC"
        version_id = (
            wrapper.commit_id
            if wrapper.commit_id
            else client.version.get_versions(
                wrapper.model_id, wrapper.stream_id, limit=1
            )
            .items[0]
            .id
        )
    return (
        account_id,
        project_id,
        project_name,
        model_id,
        model_name,
        version_id,
        load_option,
    )


def check_project_permissions(client, project, workspace_id=None) -> Tuple[bool, str]:
    """
    check if the user has permission to receive from a project.
    """
    # check if user is workspace admin
    is_workspace_admin = False
    if workspace_id and workspace_id != "personal":
        try:
            workspace = client.workspace.get(workspace_id)
            if workspace and workspace.role:
                is_workspace_admin = "workspace:admin" in workspace.role
        except Exception as e:
            print(f"Cannot access workspace: {e}")

    elif not workspace_id and hasattr(project, "workspace_id") and project.workspace_id:
        try:
            workspace = client.workspace.get(project.workspace_id)
            if workspace and workspace.role:
                is_workspace_admin = "workspace:admin" in workspace.role
        except Exception as e:
            print(f"Cannot access workspace: {e}")

    # check permission
    role = getattr(project, "role", "")
    can_receive = False
    error_message = ""

    if role:
        if is_workspace_admin:
            can_receive = "stream:reviewer" not in role
        else:
            can_receive = any(r in role for r in ["stream:owner", "stream:contributor"])
    else:
        can_receive = is_workspace_admin

    if not can_receive:
        error_message = "Your role on this project doesn't give you permission to load."

    return can_receive, error_message
