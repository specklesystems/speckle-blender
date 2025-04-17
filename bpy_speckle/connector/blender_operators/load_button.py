import bpy
from typing import Set
from bpy.types import Context
from ..operations.load_operation import load_operation
from ..utils.account_manager import get_server_url_by_account_id


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: Context, event: bpy.types.Event) -> Set[str]:
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager
        model_card = context.scene.speckle_state.model_cards.add()
        model_card.server_url = get_server_url_by_account_id(wm.selected_account_id)
        model_card.project_id = wm.selected_project_id
        model_card.project_name = wm.selected_project_name
        model_card.model_id = wm.selected_model_id
        model_card.model_name = wm.selected_model_name
        model_card.is_publish = False
        model_card.load_option = wm.selected_version_load_option
        model_card.version_id = wm.selected_version_id

        # Load selected model version
        load_operation(context)

        # Clear selected model details from Window Manager
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        return {"FINISHED"}
