import bpy
import webbrowser
from typing import Set
from bpy.types import Event, Context, UILayout

class SPECKLE_OT_model_card_settings(bpy.types.Operator):
    """Manages settings and actions for a Speckle model card.


    Attributes:
        model_name (StringProperty): Name of the model being configured.
    """
    bl_idname = "speckle.model_card_settings"
    bl_label = "Model Card Settings"
    bl_description = "Settings for the model card"
    model_card_index: bpy.props.IntProperty(name="Model Card Index", default=0) # type: ignore

    def execute(self, context: Context) -> Set[str]:
        return {'FINISHED'}
    
    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        # Add a button for viewing 3d model in the browser
        layout.operator("speckle.view_in_browser", text="View in Browser").model_card_index = self.model_card_index
        # Add a button for viewing model versions in the browser
        layout.operator("speckle.view_model_versions", text="View Model Versions").model_card_index = self.model_card_index
        # Add a separator
        layout.separator()
        row = layout.row()
        # Add a button for deleting the model card
        row.alert = True
        delete_op = row.operator("speckle.delete_model_card", text="Delete Model Card", icon='TRASH')
        delete_op.model_card_index = self.model_card_index

    def invoke(self, context: Context, event: Event) -> Set[str]:
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

# Operator for viewing the model in the browser
class SPECKLE_OT_view_in_browser(bpy.types.Operator):
    """Opens the current model in the Speckle web viewer.

    This operator opens the default web browser to display the current
    model in the Speckle web app.
    """
    bl_idname = "speckle.view_in_browser"
    bl_label = "View in Browser"
    bl_description = "View the model in the browser"

    model_card_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context: Context) -> Set[str]:
        model_card = context.scene.speckle_state.model_cards[self.model_card_index]
        url = f"{model_card.server_url}/projects/{model_card.project_id}/models/{model_card.model_id}"
        webbrowser.open(url)
        self.report({'INFO'}, f"Viewing in the browser: {url}")
        return {'FINISHED'}

# Operator for viewing the model versions in the browser
class SPECKLE_OT_view_model_versions(bpy.types.Operator):
    """Opens the model's version history in the Speckle web app.

    This operator opens the default web browser to display the version
    history of the current model in the Speckle web app.
    """
    bl_idname = "speckle.view_model_versions"
    bl_label = "View Model Versions"
    bl_description = "View the model versions in the browser"

    model_card_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context: Context) -> Set[str]:
        model_card = context.scene.speckle_state.model_cards[self.model_card_index]
        url = f"{model_card.server_url}/projects/{model_card.project_id}/models/{model_card.model_id}/versions"
        webbrowser.open(url)

        self.report({'INFO'}, "Viewing model's versions in the browser")
        return {'FINISHED'}

# Operator for deleting a model card
class SPECKLE_OT_delete_model_card(bpy.types.Operator):
    """Deletes a Speckle model card from the Blender UI.

    This operator removes a model card from the collection of model cards
    in the Speckle state after confirming with the user.
    """
    bl_idname = "speckle.delete_model_card"
    bl_label = "Delete Model Card"
    bl_description = "Delete this model card"

    model_card_index: bpy.props.IntProperty() #type: ignore

    def execute(self, context: Context) -> Set[str]:
        # Get the model card name for the report message
        model_card = context.scene.speckle_state.model_cards[self.model_card_index]
        model_name = model_card.model_name
        
        # Remove the model card from the collection
        context.scene.speckle_state.model_cards.remove(self.model_card_index)
        
        # Report success
        self.report({'INFO'}, f"Model card '{model_name}' has been deleted")
        return {'FINISHED'}
    
    def invoke(self, context: Context, event: Event) -> Set[str]:
        # Show a confirmation dialog
        return context.window_manager.invoke_confirm(self, event)