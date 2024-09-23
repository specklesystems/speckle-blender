import bpy

# Load Operator
class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def execute(self, context):
        context.scene.speckle_ui_mode = "LOAD"
        self.report({'INFO'}, "Load button clicked")
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")
        return {'FINISHED'}