import bpy
import webbrowser
from typing import Set
from bpy.types import Event, Context, UILayout


class SPECKLE_OT_model_card_settings(bpy.types.Operator):
    """
    manages settings and actions for a Speckle model card
    """

    bl_idname = "speckle.model_card_settings"
    bl_label = "Model Card Settings"
    bl_description = "More options for the model card"
    model_card_id: bpy.props.StringProperty(name="Model Card ID", default="")  # type:ignore

    def execute(self, context: Context) -> Set[str]:
        return {"FINISHED"}

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.operator(
            "speckle.view_in_browser", text="View in Browser"
        ).model_card_id = self.model_card_id
        layout.operator(
            "speckle.view_model_versions", text="View Model Versions"
        ).model_card_id = self.model_card_id
        layout.separator()
        row = layout.row()
        # add a button for deleting the model card
        row.alert = True
        delete_op = row.operator(
            "speckle.delete_model_card", text="Delete Model Card", icon="TRASH"
        )
        delete_op.model_card_id = self.model_card_id

    def invoke(self, context: Context, event: Event) -> Set[str]:
        wm = context.window_manager
        return wm.invoke_popup(self)


class SPECKLE_OT_view_in_browser(bpy.types.Operator):
    """
    opens the current model in the Speckle web viewer
    """

    bl_idname = "speckle.view_in_browser"
    bl_label = "View in Browser"
    bl_description = "View the model in the browser"

    model_card_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        url = f"{model_card.server_url}/projects/{model_card.project_id}/models/{model_card.model_id}"
        webbrowser.open(url)
        self.report({"INFO"}, f"Viewing in the browser: {url}")
        return {"FINISHED"}


class SPECKLE_OT_view_model_versions(bpy.types.Operator):
    """
    opens the model's version history in the Speckle web app
    """

    bl_idname = "speckle.view_model_versions"
    bl_label = "View Model Versions"
    bl_description = "View the model versions in the browser"

    model_card_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        url = f"{model_card.server_url}/projects/{model_card.project_id}/models/{model_card.model_id}/versions"
        webbrowser.open(url)

        self.report({"INFO"}, "Viewing model's versions in the browser")
        return {"FINISHED"}


class SPECKLE_OT_delete_model_card(bpy.types.Operator):
    """
    deletes a Speckle model card from the Blender UI
    """

    bl_idname = "speckle.delete_model_card"
    bl_label = "Delete Model Card"
    bl_description = "Delete this model card"

    model_card_id: bpy.props.StringProperty()  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        model_name = model_card.model_name

        # find the index of the model card and remove it
        for i, card in enumerate(context.scene.speckle_state.model_cards):
            if card.get_model_card_id() == self.model_card_id:
                context.scene.speckle_state.model_cards.remove(i)
                break

        self.report({"INFO"}, f"Model card '{model_name}' has been deleted")
        context.window.screen = context.window.screen

        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return self.execute(context)
