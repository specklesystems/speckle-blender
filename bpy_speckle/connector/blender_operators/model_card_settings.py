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
        self.report({'INFO'}, f"Settings for {context.scene.speckle_state.model_cards[self.model_card_index]}")
        return {'FINISHED'}
    
    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        # Add a button for viewing 3d model in the browser
        layout.operator("speckle.view_in_browser", text="View in Browser").model_card_index = self.model_card_index
        # Add a button for viewing model versions in the browser
        layout.operator("speckle.view_model_versions", text="View Model Versions").model_card_index = self.model_card_index

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
