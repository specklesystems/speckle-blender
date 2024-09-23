import bpy

# Publish Operator
class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"

    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    def execute(self, context):
        context.scene.speckle_ui_mode = "PUBLISH"
        self.report({'INFO'}, "Publish button clicked")
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")
        return {'FINISHED'}