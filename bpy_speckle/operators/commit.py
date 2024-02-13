"""
Commit operators
"""
import bpy
from bpy.props import BoolProperty
from bpy_speckle.clients import speckle_clients
from bpy_speckle.functions import _report
from bpy_speckle.properties.scene import get_speckle
from specklepy.logging import metrics


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
        if not self.are_you_sure:
            _report("Cancelled by user")
            return {"CANCELLED"}
        self.are_you_sure = False

        self.delete_commit(context)
        return {"FINISHED"}

    @staticmethod
    def delete_commit(context: bpy.types.Context) -> None: 
        speckle = get_speckle(context)

        (_, stream, _, commit) = speckle.validate_commit_selection()

        client = speckle_clients[int(speckle.active_user)]

        deleted = client.commit.delete(stream_id=stream.id, commit_id=commit.id)

        metrics.track(
            "Connector Action",
            client.account, 
            custom_props={
                "name": "delete_commit"
            },
        )
        
        if not deleted:
            raise Exception("Delete operation failed")

        print(f"Commit {commit.id} ({commit.message}) has been deleted from stream {stream.id}")

