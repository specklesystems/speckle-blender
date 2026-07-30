import bpy
from typing import Set
from bpy.types import Context
from ..operations.load_operation import load_operation
from ..utils.account_manager import get_server_url_by_account_id
from ..utils.model_card_utils import (
    update_model_card_objects,
    delete_model_card_objects,
    model_card_exists,
)


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load model"
    bl_description = "Load selection from Speckle"

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager
        if model_card_exists(
            wm.selected_project_id, wm.selected_model_id, False, context
        ):
            model_card = context.scene.speckle_state.get_model_card_by_id(
                f"{wm.ui_mode}-{wm.selected_project_id}-{wm.selected_model_id}"
            )
            delete_model_card_objects(model_card, context)
        else:
            model_card = context.scene.speckle_state.model_cards.add()
        model_card.account_id = wm.selected_account_id
        model_card.server_url = get_server_url_by_account_id(wm.selected_account_id)
        model_card.project_id = wm.selected_project_id
        model_card.project_name = wm.selected_project_name
        model_card.model_id = wm.selected_model_id
        model_card.model_name = wm.selected_model_name
        model_card.is_publish = False
        model_card.load_option = wm.selected_version_load_option
        model_card.version_id = wm.selected_version_id
        model_card.instance_loading_mode = wm.instance_loading_mode

        converted_objects = load_operation(context, wm.instance_loading_mode)
        update_model_card_objects(model_card, converted_objects)

        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        return {"FINISHED"}
