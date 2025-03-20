import bpy
from typing import Set
from bpy.types import Context


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: Context, event: bpy.types.Event) -> Set[str]:
        # Captures cursor position for UI placement
        context.scene.speckle_state.mouse_position = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        # Sets the UI mode to LOAD
        context.scene.speckle_state.ui_mode = "LOAD"
        # Logs cursor position
        self.report(
            {"INFO"},
            f"Load button clicked at {context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1]}",
        )
        # Opens project_selection_dialog
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")

        return {"FINISHED"}
