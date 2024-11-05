"""
User account operators
"""
from typing import cast

import bpy
from bpy.types import Context
from specklepy.core.api.client import SpeckleClient
from specklepy.core.api.credentials import Account, get_local_accounts
from specklepy.core.api.models import Stream
from specklepy.logging import metrics

from bpy_speckle.clients import speckle_clients
from bpy_speckle.functions import _report
from bpy_speckle.properties.scene import (SpeckleSceneSettings,
                                          SpeckleStreamObject,
                                          SpeckleUserObject, get_speckle,
                                          restore_selection_state)


class ResetUsers(bpy.types.Operator):
    """
    Reset loaded users
    """

    bl_idname = "speckle.users_reset"
    bl_label = "Reset Users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        self.reset_ui(context)

        metrics.track(
            "Connector Action",
            None,
            custom_props={"name": "ResetUsers"},
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
    Loads all user accounts from the credentials in the local database.
    See docs to add accounts via Manager
    """

    bl_idname = "speckle.users_load"
    bl_label = "Load Users"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Loads all user accounts from the credentials in the local database.\nSee docs to add accounts via Manager"

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
            raise Exception(
                "Zero accounts were found, please add one through Speckle Manager or a local account"
            )

        for profile in profiles:
            try:
                add_user_account(profile, speckle)
            except Exception as ex:
                _report(
                    f"Failed to authenticate user account {profile.userInfo.email} with server {profile.serverInfo.url}: {ex}"
                )
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
            raise Exception(
                "Zero valid user accounts were found, please ensure account is valid and the server is running"
            )

        return {"FINISHED"}


def add_user_account(
    account: Account, speckle: SpeckleSceneSettings
) -> SpeckleUserObject:
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

    assert URL
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

    _report(f"Adding stream {s.id} - {s.name}")

    if stream.branches:
        s.load_stream_branches(stream)


class LoadUserStreams(bpy.types.Operator):
    """
    (Re)Load all available projects for active user
    """

    bl_idname = "speckle.load_user_streams"
    bl_label = "Load User's Projects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "(Re)Load all available projects for active user"

    stream_limit: int = 20
    branch_limit: int = 100
    commits_limit: int = 10

    def execute(self, context):
        self.load_user_stream(context)
        return {"FINISHED"}

    def load_user_stream(self, context: Context) -> None:
        speckle = get_speckle(context)

        user = speckle.validate_user_selection()

        client = speckle_clients[int(speckle.active_user)]
        try:
            streams = client.stream.list(stream_limit=self.stream_limit)
        except Exception as ex:
            raise Exception("Failed to retrieve projects") from ex

        if not streams:
            _report("Zero projects found")
            return

        active_stream_id = None
        if active_stream := user.get_active_stream():
            active_stream_id = active_stream.id
        elif len(user.streams) > 0:
            active_stream_id = user.streams[0].id

        user.streams.clear()

        for i, s in enumerate(streams):
            assert s.id
            load_branches = s.id == active_stream_id if active_stream_id else i == 0
            if load_branches:
                sstream = client.stream.get(
                    id=s.id, branch_limit=self.branch_limit, commit_limit=10
                )
                add_user_stream(user, sstream)
            else:
                add_user_stream(user, s)

        restore_selection_state(speckle)

        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        metrics.track(
            "Connector Action",
            client.account,
            custom_props={"name": "LoadUserStreams"},
        )
