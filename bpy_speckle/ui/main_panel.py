import bpy

# Main Panel
class SPECKLE_PT_main_panel(bpy.types.Panel):
    bl_label = "Speckle"

    bl_idname = "SPECKLE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Speckle'

    def draw(self, context):
        layout = self.layout
        
        # Check to see if there are any speckle models in the file
        if not context.scene.speckle_model_cards:
            layout.label(text="Hello!") 
            layout.label(text="There are no Speckle models in this file yet.")
        
        # Add some space
        layout.separator()
        
        # Publish and Load buttons
        row = layout.row()
        row.operator("speckle.publish", text="Publish", icon='EXPORT')
        row.operator("speckle.load", text="Load", icon='IMPORT')

        layout.separator()

        for model_card in context.scene.speckle_model_cards:
            box = layout.box()
            row = box.row()
            icon = 'EXPORT' if model_card.is_publish else 'IMPORT'
            row.label(icon=icon)
            row.label(text=model_card.model_name)
            row.label(text=model_card.project_name)
            row.operator("speckle.model_card_settings", text="", icon='PREFERENCES').model_name = model_card.model_name
            # Display selection summary or version ID
            if model_card.is_publish:
                box.label(text=f"Selection: {model_card.selection_summary}")
            else:
                box.label(text=f"Version ID: {model_card.version_id}")


