"""
User account operators
"""
from typing import List, cast
import bpy
from bpy.types import Context
from bpy_speckle.functions import _report
from bpy_speckle.clients import speckle_clients
from bpy_speckle.properties.scene import SpeckleBranchObject, SpeckleCommitObject, SpeckleSceneSettings, SpeckleStreamObject, SpeckleUserObject, get_speckle
from specklepy.core.api.client import SpeckleClient
from specklepy.core.api.models import Stream
from specklepy.core.api.credentials import get_local_accounts, Account
from specklepy.logging import metrics

class ResetUsers(bpy.types.Operator):
    """
    Reset loaded users
    """

    bl_idname = "speckle.users_reset"
    bl_label = "Reset users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        self.reset_ui(context)

        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "ResetUsers"
            },
        )

        bpy.context.view_layer.update()
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}

    @staticmethod
    def reset_ui(context: Context):
        speckle = get_speckle(context)

        speckle.users.clear()
        speckle_clients.clear()

class LoadUsers(bpy.types.Operator):
    """
    Load all users from local user database
    """

    bl_idname = "speckle.users_load"
    bl_label = "Load users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        _report("Loading users...")

        speckle = get_speckle(context)
        users_list = speckle.users

        ResetUsers.reset_ui(context)

        profiles = get_local_accounts()
        active_user_index = 0

        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "LoadUsers",
            },
        )

        if not profiles:
            raise Exception("Zero accounts were found, please add one through Speckle Manager or a local account")

        for profile in profiles:
            try:
                add_user_account(profile, speckle)
            except Exception as ex:
                _report(f"Failed to authenticate user account {profile.userInfo.email} with server {profile.serverInfo.url}: {ex}")
                users_list.remove(len(users_list) - 1)
                continue

            if profile.isDefault:
                active_user_index = len(users_list) - 1

        _report(f"Authenticated {len(users_list)}/{len(profiles)} accounts")

        if active_user_index < len(users_list):
            speckle.active_user = str(active_user_index)

        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        if not users_list:
            raise Exception("Zero valid user accounts were found, please ensure account is valid and the server is running")

        return {"FINISHED"}

def add_user_account(account: Account, speckle: SpeckleSceneSettings) -> SpeckleUserObject:
    """Creates a new new SpeckleUserObject for the provided user Account and adds it to the SpeckleSceneSettings"""
    users_list = speckle.users

    URL = account.serverInfo.url

    user = cast(SpeckleUserObject, users_list.add())
    user.server_name = account.serverInfo.name or "Speckle Server"
    user.server_url = URL
    user.id = account.userInfo.id
    user.name = account.userInfo.name
    user.email = account.userInfo.email
    user.company = account.userInfo.company or ""

    assert(URL)
    client = SpeckleClient(
        host=URL,
        use_ssl="https" in URL,
    )
    client.authenticate_with_account(account)
    speckle_clients.append(client)
    return user


def add_user_stream(user: SpeckleUserObject, stream: Stream):
    """Adds the provided Stream (with branch & commits) to the SpeckleUserObject"""
    s = cast(SpeckleStreamObject, user.streams.add())
    s.name = stream.name
    s.id = stream.id
    s.description = stream.description

    if not stream.branches:
        return

    # branches = [branch for branch in stream.branches.items if branch.name != "globals"]
    for b in stream.branches.items:
        branch = cast(SpeckleBranchObject, s.branches.add())
        branch.name = b.name
        branch.id = b.id
        branch.description = b.description

        if not b.commits:
            continue

        for c in b.commits.items:
            commit: SpeckleCommitObject = branch.commits.add()
            commit.id = commit.name = c.id
            commit.message = c.message or ""
            commit.author_name = c.authorName
            commit.author_id = c.authorId
            commit.created_at = c.createdAt.strftime("%Y-%m-%d %H:%M:%S.%f%Z") if c.createdAt else ""
            commit.source_application = str(c.sourceApplication)
            commit.referenced_object = c.referencedObject

    if hasattr(s, "baseProperties"):
        s.units = stream.baseProperties.units # type: ignore
    else:
        s.units = "Meters"


class LoadUserStreams(bpy.types.Operator):
    """
    Load all available streams for active user
    """

    bl_idname = "speckle.load_user_streams"
    bl_label = "Load user streams"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "(Re)load all available user streams"

    stream_limit: int = 20
    branch_limit: int = 100

    def execute(self, context):
        try:
            self.load_user_stream(context)
            return {"FINISHED"}
        except Exception as ex:
            _report(f"{self.bl_idname} failed: {ex}")
            return {"CANCELLED"} 
        
    def load_user_stream(self, context: Context) -> None:
        speckle = get_speckle(context)

        user = speckle.validate_user_selection()

        client = speckle_clients[int(speckle.active_user)]
        try:
            streams = client.stream.list(stream_limit=self.stream_limit)
        except Exception as ex:
            raise Exception(f"Failed to retrieve streams") from ex
        
        if not streams:
            raise Exception("Zero streams found")
            return

        user.streams.clear()

        for s in streams:
            assert(s.id)
            sstream = client.stream.get(id=s.id, branch_limit=self.branch_limit)
            add_user_stream(user, sstream)

        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
                
        metrics.track(
            "Connector Action",
            client.account, 
            custom_props={
                "name": "LoadUserStreams"
            },
        )


