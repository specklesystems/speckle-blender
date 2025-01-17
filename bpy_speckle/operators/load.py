import bpy
from typing import Set

# Load Operator
class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        context.scene.speckle_state.mouse_position = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        context.scene.speckle_state.ui_mode = "LOAD"
        self.report({'INFO'}, f"Load button clicked at {context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1]}")
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")
        return {'FINISHED'}