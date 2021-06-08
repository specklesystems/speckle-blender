"""
Speckle UI elements for the 3d viewport
"""


import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    CollectionProperty,
    EnumProperty,
)

import datetime

"""
Compatibility 
TODO: evaluate if we should still support Blender <2.80
"""

Region = "TOOLS" if bpy.app.version < (2, 80, 0) else "UI"


def wrap(width, text):
    """
    Split strings into width for
    wrapping
    """
    lines = []

    arr = text.split()
    lengthSum = 0

    line = []
    for var in arr:
        lengthSum += len(var) + 1
        if lengthSum <= width:
            line.append(var)
        else:
            lines.append(" ".join(line))
            line = [var]
            lengthSum = len(var)

    lines.append(" ".join(line))

    return lines


def get_available_users(self, context):
    """
    Function to populate users list
    """
    return [(a, a, a.name) for a in context.scene.speckle.users]


class VIEW3D_UL_SpeckleUsers(bpy.types.UIList):
    """
    Speckle user list
    """

    def draw_item(self, context, layout, data, user, active_data, active_propname):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if user:
                # layout.prop(user, "name", text=user.name, emboss=False, icon_value=0)
                layout.label(
                    text=user.name + " (" + user.email + ")",
                    translate=False,
                    icon_value=0,
                )
            else:
                layout.label(text="", translate=False, icon_value=0)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="Users", icon_value=0)


class VIEW3D_UL_SpeckleStreams(bpy.types.UIList):
    """
    Speckle stream list
    """

    def draw_item(self, context, layout, data, stream, active_data, active_propname):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if stream:
                # layout.prop(user, "name", text=user.name, emboss=False, icon_value=0)
                layout.label(
                    text="{} ({})".format(stream.name, stream.id),
                    translate=False,
                    icon_value=0,
                )
            else:
                layout.label(text=" ", translate=False, icon_value=0)

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="Streams", icon_value=0)


class VIEW3D_PT_SpeckleUser(bpy.types.Panel):
    """
    Speckle Users UI panel in the 3d viewport
    """

    bl_space_type = "VIEW_3D"
    bl_region_type = Region
    bl_category = "Speckle"
    bl_context = "objectmode"
    bl_label = "User"

    def draw(self, context):
        speckle = context.scene.speckle

        layout = self.layout
        col = layout.column()

        if len(speckle.users) < 1:
            col.label(text="No users found.")
        else:
            # col.label(text="User")
            col.prop(speckle, "active_user", text="")
            user = speckle.users[int(speckle.active_user)]
            col.label(text="{} ({})".format(user.server_name, user.server_url))
            col.label(text="{} ({})".format(user.name, user.email))


class VIEW3D_PT_SpeckleStreams(bpy.types.Panel):
    """
    Speckle Streams UI panel in the 3d viewport
    """

    bl_space_type = "VIEW_3D"
    bl_region_type = Region
    bl_category = "Speckle"
    bl_context = "objectmode"
    bl_label = "Streams"

    def draw(self, context):
        speckle = context.scene.speckle
        col = self.layout.column()

        if len(speckle.users) < 1:
            col.label(text="No stream data.")
        else:
            user = speckle.users[int(speckle.active_user)]
            # col.label(text="Streams")
            col.template_list(
                "VIEW3D_UL_SpeckleStreams", "", user, "streams", user, "active_stream"
            )
            row = col.row(align=True)
            row.operator("speckle.create_stream", text="", icon="ADD")
            row.operator("speckle.delete_stream", text="", icon="REMOVE")
            row.operator("speckle.load_user_streams", text="", icon="FILE_REFRESH")


class VIEW3D_PT_SpeckleActiveStream(bpy.types.Panel):
    """
    Speckle Active Streams UI panel in the 3d viewport
    """

    bl_space_type = "VIEW_3D"
    bl_region_type = Region
    bl_category = "Speckle"
    bl_context = "objectmode"
    bl_label = "Active stream"

    def draw(self, context):
        speckle = context.scene.speckle
        col = self.layout.column()

        if len(speckle.users) < 1:
            col.label(text="No stream data.")
        else:
            user = speckle.users[int(speckle.active_user)]
            if len(user.streams) < 1:
                col.label(text="No active stream.")
            else:
                stream = user.streams[user.active_stream]
                # user.active_stream = min(user.active_stream, len(user.streams) - 1)
                row = col.row()
                row.label(text="{} ({})".format(stream.name, stream.id))
                row.operator("speckle.stream_copy_id", text="", icon="COPY_ID")
                col.separator()

                row = col.row()
                row.prop(stream, "branch", text="")
                row.operator("speckle.branch_copy_name", text="", icon="COPY_ID")

                if len(stream.branches) > 0:
                    branch = stream.branches[int(stream.branch)]

                    row = col.row()
                    row.prop(branch, "commit", text="")
                    row.operator("speckle.commit_copy_id", text="", icon="COPY_ID")

                    if len(branch.commits) > 0:
                        commit = branch.commits[int(branch.commit)]
                        area = col.box()
                        area.separator()

                        lines = wrap(32, commit.message)
                        for line in lines:
                            row = area.row(align=True)
                            row.alignment = "EXPAND"
                            row.scale_y = 0.4
                            row.label(text=line)
                        area.separator()

                        dt = datetime.datetime.strptime(
                            commit.created_at, "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                        col.label(text="{}".format(dt.ctime()))
                        col.label(
                            text="{} ({})".format(commit.author_name, commit.author_id)
                        )
                        col.label(text=commit.source_application)
                else:
                    col.label(text="No branches found!")

                col.separator()

                area = col.box()
                row = area.row()
                subcol = row.column()
                subcol.operator("speckle.receive_stream_objects", text="Receive")
                subcol.prop(speckle, "receive_script", text="")
                subcol = row.column()
                subcol.operator("speckle.send_stream_objects", text="Send")
                subcol.prop(speckle, "send_script", text="")
                area.prop(stream, "query", text="Filter")

                col.separator()

                row = col.row(align=True)
                subcol = row.column()
                subcol.label(text="Units:")
                subcol = row.column()
                subcol.label(text=stream.units)

                col.label(text="Description:")
                area = col.box()
                area.separator()

                lines = wrap(32, stream.description)

                for line in lines:
                    row = area.row(align=True)
                    row.alignment = "EXPAND"
                    row.scale_y = 0.4
                    row.label(text=line)

                area.separator()
                col.separator()
                col.operator("speckle.view_stream_data_api", text="Open Stream in Web")
