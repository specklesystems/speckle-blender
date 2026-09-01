import traceback
from typing import Set

import bpy
from bpy.types import Context
from ..operations.load_operation import load_operation
from ..speckle_api import get_server_url_by_account_id
from ..utils.model_card_utils import (
    update_model_card_objects,
    delete_model_card_objects,
    format_load_summary,
)


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load model"
    bl_description = "Load selection from Speckle"

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        # Re-loading has to delete the previous objects *before* loading: they
        # share applicationIds with their replacements, and
        # delete_model_card_objects resolves by applicationId, so deleting
        # afterwards could remove the copy we just loaded. Clear the card's
        # object lists to match, or a failed load below leaves the card
        # referencing data-blocks that no longer exist.
        existing_card = context.scene.speckle_state.find_model_card(
            wm.selected_project_id, wm.selected_model_id, is_publish=False
        )
        if existing_card is not None:
            delete_model_card_objects(existing_card, context)
            existing_card.objects.clear()
            existing_card.collections.clear()

        # A bundle version that fails to read raises by design, so guard the
        # load and only touch the model card once it has succeeded — otherwise
        # a failure leaves a phantom card for a version that never arrived.
        try:
            converted_objects = load_operation(
                context,
                wm.selected_account_id,
                wm.selected_project_id,
                wm.selected_model_id,
                wm.selected_version_id,
                wm.selected_model_name,
                wm.instance_loading_mode,
            )
        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, f"Load failed: {e}")
            return {"CANCELLED"}

        model_card = (
            existing_card
            if existing_card is not None
            else context.scene.speckle_state.model_cards.add()
        )
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
        update_model_card_objects(model_card, converted_objects)

        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        self.report({"INFO"}, format_load_summary(model_card))

        return {"FINISHED"}
