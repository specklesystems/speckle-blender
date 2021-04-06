"""
User account operators
"""

import bpy, bmesh, os
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    CollectionProperty,
    EnumProperty,
)
from bpy_speckle.properties.scene import SpeckleUserObject

from bpy_speckle.functions import _report
from bpy_speckle.clients import speckle_clients

from speckle.api.client import SpeckleClient
from speckle.api.credentials import get_default_account, get_local_accounts


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
            client = SpeckleClient(host=profile.serverInfo.url, use_ssl=True)
            client.authenticate(user.authToken)
            speckle_clients.append(client)

        context.scene.speckle.active_user_index = int(context.scene.speckle.active_user)
        bpy.ops.speckle.load_user_streams()
        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


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
                streams = client.stream.list()
            except Exception as e:
                _report("Failed to retrieve streams: {}".format(e))
                return
            if not streams:
                _report("Failed to retrieve streams.")
                return

            user.streams.clear()

            streams = sorted(streams, key=lambda x: x.name, reverse=False)
            default_units = "Meters"

            for s in streams:
                stream = user.streams.add()
                stream.name = s.name
                stream.id = s.id
                stream.description = s.description

                sstream = client.stream.get(id=s.id)

                if not sstream.branches:
                    continue

                for b in sstream.branches.items:
                    branch = stream.branches.add()
                    branch.name = b.name

                    if not b.commits:
                        continue

                    for c in b.commits.items:
                        commit = branch.commits.add()
                        commit.id = c.id
                        commit.message = c.message
                        commit.author_name = c.authorName
                        commit.author_id = c.authorId
                        commit.created_at = c.createdAt
                        commit.source_application = str(c.sourceApplication)

                if hasattr(s, "baseProperties"):
                    stream.units = s.baseProperties.units
                else:
                    stream.units = default_units

            bpy.context.view_layer.update()

            return {"FINISHED"}

        if context.area:
            context.area.tag_redraw()
        return {"CANCELLED"}
