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
        
        # TODO: Add a check to see if there are any speckle models in the file
        # Add greeting text
        layout.label(text="Hello!")
        layout.label(text="There are no Speckle models in this file yet.")
        
        # Add some space
        layout.separator()
        
        # Publish and Load buttons
        row = layout.row()
        row.operator("speckle.publish", text="Publish", icon='EXPORT')
        row.operator("speckle.load", text="Load", icon='IMPORT')
