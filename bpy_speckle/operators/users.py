"""
User account operators
"""
import bpy
from bpy_speckle.functions import _report
from bpy_speckle.clients import speckle_clients
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts
from datetime import datetime


class LoadUsers(bpy.types.Operator):
    """
    Load all users from local user database
    """

    bl_idname = "speckle.users_load"
    bl_label = "Load users"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        _report("Loading users...")

        users = context.scene.speckle.users

        context.scene.speckle.users.clear()
        speckle_clients.clear()

        profiles = get_local_accounts()

        for profile in profiles:
            user = users.add()
            user.server_name = profile.serverInfo.name or "Speckle Server"
            user.server_url = profile.serverInfo.url
            user.name = profile.userInfo.name
            user.email = profile.userInfo.email
            user.company = profile.userInfo.company or ""
            user.authToken = profile.token
            try:
                client = SpeckleClient(
                    host=profile.serverInfo.url,
                    use_ssl="https" in profile.serverInfo.url,
                )
                client.authenticate(user.authToken)
                speckle_clients.append(client)
            except Exception as ex:
                _report(ex)
                users.remove(len(users) - 1)
            if profile.isDefault:
                context.scene.speckle.active_user = str(len(users) - 1)

        context.scene.speckle.active_user_index = int(context.scene.speckle.active_user)
        bpy.ops.speckle.load_user_streams()
        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


def add_user_stream(user, stream):
    s = user.streams.add()
    s.name = stream.name
    s.id = stream.id
    s.description = stream.description

    if not stream.branches:
        return

    # branches = [branch for branch in stream.branches.items if branch.name != "globals"]
    for b in stream.branches.items:
        branch = s.branches.add()
        branch.name = b.name

        if not b.commits:
            continue

        for c in b.commits.items:
            commit = branch.commits.add()
            commit.id = commit.name = c.id
            commit.message = c.message or ""
            commit.author_name = c.authorName
            commit.author_id = c.authorId
            commit.created_at = datetime.strftime(c.createdAt, "%Y-%m-%d %H:%M:%S.%f%Z")
            commit.source_application = str(c.sourceApplication)

    if hasattr(s, "baseProperties"):
        s.units = stream.baseProperties.units
    else:
        s.units = "Meters"


class LoadUserStreams(bpy.types.Operator):
    """
    Load all available streams for active user user
    """

    bl_idname = "speckle.load_user_streams"
    bl_label = "Load user streams"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "(Re)load all available user streams"

    def execute(self, context):
        speckle = context.scene.speckle

        if len(speckle.users) > 0:
            user = speckle.users[int(context.scene.speckle.active_user)]
            client = speckle_clients[int(context.scene.speckle.active_user)]

            try:
                streams = client.stream.list(stream_limit=20)
            except Exception as e:
                _report("Failed to retrieve streams: {}".format(e))
                return
            if not streams:
                _report("Failed to retrieve streams.")
                return

            user.streams.clear()

            default_units = "Meters"

            for s in streams:
                sstream = client.stream.get(id=s.id)
                add_user_stream(user, sstream)

            bpy.context.view_layer.update()

            return {"FINISHED"}

        if context.area:
            context.area.tag_redraw()
        return {"CANCELLED"}
