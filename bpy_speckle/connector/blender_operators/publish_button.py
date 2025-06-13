import bpy
from bpy.types import Context
from bpy.types import Event
from typing import Set

from ..operations.publish_operation import publish_operation
from ..utils.account_manager import get_server_url_by_account_id
from ..utils.model_card_utils import model_card_exists, update_model_card_objects


class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"
    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    version_message: bpy.props.StringProperty(name="Version Message")  # type: ignore
    apply_modifiers: bpy.props.BoolProperty(  # type: ignore
        name="Apply Modifiers",
        description="Apply all modifiers to objects before conversion",
        default=True,
    )

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.prop(self, "version_message")
        layout.prop(self, "apply_modifiers")

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        # check if we have stored objects from selection dialog
        if not wm.speckle_objects:
            self.report(
                {"ERROR"},
                "No objects selected to publish. Please use 'Select Objects' first.",
            )
            return {"CANCELLED"}

        account_id = getattr(wm, "selected_account_id", "")
        project_id = getattr(wm, "selected_project_id", "")
        model_id = getattr(wm, "selected_model_id", "")

        if not account_id:
            self.report({"ERROR"}, "No account selected")
            return {"CANCELLED"}

        if not project_id:
            self.report({"ERROR"}, "No project selected")
            return {"CANCELLED"}

        if not model_id:
            self.report({"ERROR"}, "No model selected")
            return {"CANCELLED"}

        objects_to_convert = []
        for speckle_obj in wm.speckle_objects:
            blender_obj = bpy.data.objects.get(speckle_obj.name)
            if blender_obj:
                objects_to_convert.append(blender_obj)
            else:
                self.report(
                    {"WARNING"}, f"Object '{speckle_obj.name}' not found, skipping"
                )

        if not objects_to_convert:
            self.report({"ERROR"}, "None of the selected objects could be found")
            return {"CANCELLED"}

        success, message, version_id = publish_operation(
            context, objects_to_convert, self.version_message, self.apply_modifiers
        )

        if not success:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        # create model card if operation was successful
        if hasattr(context.scene, "speckle_state") and hasattr(
            context.scene.speckle_state, "model_cards"
        ):
            if model_card_exists(wm.selected_project_id, wm.selected_model_id, context):
                model_card = context.scene.speckle_state.get_model_card_by_id(
                    f"{wm.selected_project_id}-{wm.selected_model_id}"
                )
            else:
                model_card = context.scene.speckle_state.model_cards.add()

            model_card.account_id = account_id
            model_card.server_url = get_server_url_by_account_id(account_id)
            model_card.project_id = project_id
            model_card.project_name = getattr(wm, "selected_project_name", "")
            model_card.model_id = model_id
            model_card.model_name = getattr(wm, "selected_model_name", "")
            model_card.is_publish = True
            model_card.load_option = "SPECIFIC"  # published versions are specific
            model_card.version_id = version_id
            model_card.apply_modifiers = self.apply_modifiers
            update_model_card_objects(model_card, objects_to_convert)

        # clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        self.report({"INFO"}, message)
        context.area.tag_redraw()
        return {"FINISHED"}
