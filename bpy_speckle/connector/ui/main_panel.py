"""Module for handling the main Speckle panel.
"""

import bpy
from bpy.types import UILayout, Context
from .icons import get_icon

# Main Panel
class SPECKLE_PT_main_panel(bpy.types.Panel):
    """Main panel for the Speckle addon.

    This panel serves as the primary interface for the Speckle addon:
    - Buttons for publishing and loading models
    - Model cards showing the status of each Speckle model in the file
    - Quick access to model settings and operations

    The panel is displayed in the 3D View's sidebar under the 'Speckle' category.
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
        # row.operator("speckle.publish", text="Publish", icon='EXPORT')
        row.operator("speckle.load", text="Load", icon='IMPORT')

        layout.separator()

        # Group model cards by project name
        project_groups = {}
        for model_card in context.scene.speckle_state.model_cards:
            project_name = model_card.project_name if model_card.project_name else "No Project"
            if project_name not in project_groups:
                project_groups[project_name] = []
            project_groups[project_name].append(model_card)
        
        # Render model cards grouped by project
        for project_name, model_cards in project_groups.items():
            # Create a collapsable group for each project
            project_box = layout.box()
            project_row = project_box.row()
            project_row.label(text=f"Project: {project_name}", icon='TRIA_RIGHT')
            
            # Render model cards for this project
            for model_card in model_cards:
                box: UILayout = project_box.box()
                row: UILayout = box.row()
                icon: str = 'EXPORT' if model_card.is_publish else 'IMPORT'
                row.operator("speckle.publish", text="", icon=icon)
                row.label(text=f"{model_card.model_name}")
                # Add selection button
                select_op = row.operator("speckle.select_objects", text="", icon='RESTRICT_SELECT_OFF')
                select_op.model_card_id = model_card.get_model_card_id()
                row.operator("speckle.model_card_settings", text="", icon='PREFERENCES').model_card_id = model_card.get_model_card_id()
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
                    if model_card.load_option == "LATEST":
                        split.operator("speckle.load", text="Latest")
                    if model_card.load_option == "SPECIFIC":
                        split.operator("speckle.load", text=f"{model_card.version_id}")
                    # TODO: Get last updated time
                    split.label(text="Last updated: 2 days ago")
