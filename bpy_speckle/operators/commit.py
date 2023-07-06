"""
Commit operators
"""
import bpy
from bpy.props import BoolProperty
from bpy_speckle.clients import speckle_clients
from bpy_speckle.properties.scene import get_speckle


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
        speckle = get_speckle(context)
        wm = context.window_manager
        if len(speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        try:
            self.delete_commit(context)
            return {"FINISHED"}
        except Exception as ex:
            print(f"{self.bl_idname}: failed: {ex}")
            return {"CANCELLED"}

    def delete_commit(self, context: bpy.types.Context) -> None: 

        if not self.are_you_sure:
            raise Exception("Cancelled by user")

        self.are_you_sure = False

        speckle = get_speckle(context)

        (_, stream, _, commit) = speckle.validate_commit_selection()

        client = speckle_clients[int(speckle.active_user)]

        deleted = client.commit.delete(stream_id=stream.id, commit_id=commit.id)
        if not deleted:
            raise Exception("Delete operation failed")

        print(f"{self.bl_idname}: succeeded - commit {commit.id} ({commit.message}) has been deleted from stream {stream.id}")

