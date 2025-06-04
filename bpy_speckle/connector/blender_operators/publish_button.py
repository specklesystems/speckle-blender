import bpy
from bpy.types import Context
from bpy.types import Event
from typing import Set

from ..operations.publish_operation import publish_operation
from ..utils.account_manager import get_server_url_by_account_id


class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"
    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        if not context.selected_objects and not context.active_object:
            self.report({"ERROR"}, "No objects selected to publish")
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

        objects_to_convert = context.selected_objects or [context.active_object]

        success, message, version_id = publish_operation(context, objects_to_convert)

        if not success:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        # create model card if operation was successful
        if hasattr(context.scene, "speckle_state") and hasattr(
            context.scene.speckle_state, "model_cards"
        ):
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
            model_card.collection_name = (
                f"{getattr(wm, 'selected_model_name', 'Model')} - {version_id[:8]}"
            )

        # clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        self.report({"INFO"}, message)
        return {"FINISHED"}
