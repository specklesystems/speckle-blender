import bpy

class SPECKLE_OT_model_card_settings(bpy.types.Operator):
    bl_idname = "speckle.model_card_settings"
    bl_label = "Model Card Settings"
    bl_description = "Settings for the model card"
    model_name: bpy.props.StringProperty()

    def execute(self, context):
        self.report({'INFO'}, f"Settings for {self.model_name}")
        return {'FINISHED'}

