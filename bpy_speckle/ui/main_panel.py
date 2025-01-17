import bpy
from bpy.types import UILayout, Context, Operator
from .icons import get_icon

# Main Panel
class SPECKLE_PT_main_panel(bpy.types.Panel):
    """
    Main panel for the Speckle addon in Blender.

    This panel provides the primary user interface such as buttons for publishing and loading models, and model cards for each model added to the file.
    """
    bl_label = "Speckle"

    bl_idname = "SPECKLE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Speckle'

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.label(text="Speckle Connector BETA", icon_value=get_icon("speckle_logo"))

        # Check to see if there are any speckle models in the file
        if not context.scene.speckle_state.model_cards:
            layout.label(text="Hello!")
            layout.label(text="There are no Speckle models in this file yet.")

        # Add some space
        layout.separator()

        # Publish and Load buttons
        row: UILayout = layout.row()
        row.operator("speckle.publish", text="Publish", icon='EXPORT')
        row.operator("speckle.load", text="Load", icon='IMPORT')

        layout.separator()

        for model_card in context.scene.speckle_state.model_cards:
            box: UILayout = layout.box()
            row: UILayout = box.row()
            icon: str = 'EXPORT' if model_card.is_publish else 'IMPORT'
            row.operator("speckle.publish", text="", icon=icon)
            row.label(text=f"{model_card.model_name} - {model_card.project_name}")
            row.operator("speckle.model_card_settings", text="", icon='PREFERENCES').model_name = model_card.model_name
            row: UILayout = box.row()
            # Display selection summary or version ID
            if model_card.is_publish:
                # This adjusts the layout of the row (button 1/3, label 2/3 )
                split: UILayout = row.split(factor=0.33)
                # TODO: Connect to selection operator
                split.operator("speckle.publish", text="Selection")
                split.label(text=f"{model_card.selection_summary}")
            else:
                # This adjusts the layout of the row (button 1/3, label 2/3 )
                split: UILayout = row.split(factor=0.33)
                # TODO: Connect to version operator
                split.operator("speckle.load", text=f"{model_card.version_id}")
                # TODO: Get last updated time
                split.label(text="Last updated: 2 days ago")
