"""
Scene properties
"""
import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
)


class SpeckleSceneObject(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="")


class SpeckleCommitObject(bpy.types.PropertyGroup):
    id: StringProperty(default="abc")
    message: StringProperty(default="A simple commit")
    author_name: StringProperty(default="Author name")
    author_id: StringProperty(default="Author ID")
    created_at: StringProperty(default="Today")
    source_application: StringProperty(default="Unknown")


class SpeckleBranchObject(bpy.types.PropertyGroup):
    def get_commits(self, context):
        if self.commits != None and len(self.commits) > 0:
            return [
                (str(i), commit.id, commit.message, i)
                for i, commit in enumerate(self.commits)
            ]
        return [("0", "<none>", "<none>", 0)]

    name: StringProperty(default="main")
    commits: CollectionProperty(type=SpeckleCommitObject)
    commit: EnumProperty(
        name="Commit",
        description="Active commit",
        items=get_commits,
    )


class SpeckleStreamObject(bpy.types.PropertyGroup):
    def get_branches(self, context):
        if self.branches:
            return [
                (str(i), branch.name, branch.name, i)
                for i, branch in enumerate(self.branches)
                if branch.name != "globals"
            ]
        return [("0", "<none>", "<none>", 0)]

    name: StringProperty(default="SpeckleStream")
    description: StringProperty(default="No description provided.")
    id: StringProperty(default="")
    units: StringProperty(default="Meters")
    query: StringProperty(default="")
    branches: CollectionProperty(type=SpeckleBranchObject)
    branch: EnumProperty(
        name="Branch",
        description="Active branch",
        items=get_branches,
    )


class SpeckleUserObject(bpy.types.PropertyGroup):
    server_name: StringProperty(default="SpeckleXYZ")
    server_url: StringProperty(default="https://speckle.xyz")
    name: StringProperty(default="Speckle User")
    email: StringProperty(default="user@speckle.xyz")
    company: StringProperty(default="SpeckleSystems")
    streams: CollectionProperty(type=SpeckleStreamObject)
    active_stream: IntProperty(default=0)


class SpeckleSceneSettings(bpy.types.PropertyGroup):
    def get_scripts(self, context):
        return [
            ("<none>", "<none>", "<none>"),
            *[(t.name, t.name, t.name) for t in bpy.data.texts],
        ]

    streams: EnumProperty(
        name="Available streams",
        description="Available streams associated with user.",
        items=[],
    )

    users: CollectionProperty(type=SpeckleUserObject)

    def get_users(self, context):
        return [
            (str(i), "{} ({})".format(user.email, user.server_name), user.server_url, i)
            for i, user in enumerate(self.users)
        ]

    def set_user(self, context):
        bpy.ops.speckle.load_user_streams()

    active_user: EnumProperty(
        items=get_users,
        name="User",
        description="Select user",
        update=set_user,
        get=None,
        set=None,
    )

    objects: CollectionProperty(type=SpeckleSceneObject)

    scale: FloatProperty(default=0.001)

    user: StringProperty(
        name="User",
        description="Current user.",
        default="Speckle User",
    )

    receive_script: EnumProperty(
        name="Receive script",
        description="Script to run when receiving stream objects.",
        items=get_scripts,
    )

    send_script: EnumProperty(
        name="Send script",
        description="Script to run when sending stream objects.",
        items=get_scripts,
    )
