"""
Commit operators
"""
import bpy
from bpy.props import BoolProperty
from bpy_speckle.functions import _check_speckle_client_user_stream, _report
from bpy_speckle.clients import speckle_clients
from bpy_speckle.properties.scene import SpeckleSceneSettings


class DeleteCommit(bpy.types.Operator):
    """
    Deletes the selected commit from the selected stream.
    To execute from code, call: `bpy.ops.speckle.delete_commit(are_you_sure=True)`
    """

    bl_idname = "speckle.delete_commit"
    bl_label = "Delete commit"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Delete active commit permanently"

    are_you_sure: BoolProperty(
        name="Confirm",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "are_you_sure")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):

        if not self.are_you_sure:
            _report(f"{self.bl_idname}: cancelled by user")
            return {"CANCELLED"}

        self.are_you_sure = False

        speckle: SpeckleSceneSettings = context.scene.speckle

        user = speckle.get_active_user()
        if user is None:
            print(f"{self.bl_idname}: failed - No user selected/found")
            return {"CANCELLED"}

        stream = user.get_active_stream()
        if stream is None:
            print(f"{self.bl_idname}: failed - No stream selected/found")
            return {"CANCELLED"}

        branch = stream.get_active_branch()
        if branch is None:
            print(f"{self.bl_idname}: failed - No branch selected/found")
            return {"CANCELLED"}

        commit = branch.get_active_commit()
        if commit is None:
            print(f"{self.bl_idname}: failed - No commit selected/found")
            return {"CANCELLED"}

        client = speckle_clients[int(speckle.active_user)]

        deleted = client.commit.delete(stream_id=stream.id, commit_id=commit.id)
        if not deleted:
            print(f"{self.bl_idname}: failed - Delete operation failed")
            return {"CANCELLED"}

        print(f"{self.bl_idname}: succeeded - commit {commit.id} ({commit.message}) has been deleted from stream {stream.id}")
        return {"FINISHED"}
