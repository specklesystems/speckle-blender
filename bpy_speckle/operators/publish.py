import bpy
from bpy.types import Context
from bpy.types import Event

# Publish Operator
class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"

    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    def invoke(self, context: Context, event: Event) -> set:
        context.scene.speckle_state.mouse_position = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context: Context) -> set:
        context.scene.speckle_state.ui_mode = "PUBLISH"
        self.report({'INFO'}, f"Publish button clicked at {context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1]}")
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")
        return {'FINISHED'}