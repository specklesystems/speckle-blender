import bpy
from typing import Set
from bpy.types import Context
from ..utils.version_manager import get_latest_version
from ..operations.load_operation import load_operation
from ..utils.model_card_utils import (
    delete_model_card_objects,
    update_model_card_objects,
)


class SPECKLE_OT_load_model_card(bpy.types.Operator):
    bl_idname = "speckle.model_card_load"
    bl_label = "Load Latest from Speckle"
    bl_description = "Depending on the load option, loads the latest or a specific version from Speckle"

    model_card_id: bpy.props.StringProperty(name="Model Card ID", default="")  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        # Get the model card
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        delete_model_card_objects(model_card, context)

        # set wm
        wm.selected_account_id = model_card.account_id
        wm.selected_project_id = model_card.project_id
        wm.selected_model_name = model_card.model_name

        # if load option is set to "LATEST"
        if model_card.load_option == "LATEST":
            # get latest version from speckle
            latest_version_id, message, timestamp = get_latest_version(
                model_card.account_id, model_card.project_id, model_card.model_id
            )
            # set version id in wm
            wm.selected_version_id = latest_version_id

            # load latest version
            converted_objects = load_operation(
                context, model_card.instance_loading_mode
            )
            # update model card details
            update_model_card_objects(model_card, converted_objects)
            model_card.version_id = latest_version_id

        else:
            # set version id in wm
            wm.selected_version_id = model_card.version_id

            # load version id
            converted_objects = load_operation(
                context, model_card.instance_loading_mode
            )
            if not converted_objects:
                self.report({"ERROR"}, "Load operation failed")
                return {"CANCELLED"}
            # update model card details
            update_model_card_objects(model_card, converted_objects)

        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_version_id = ""
        wm.selected_model_name = ""

        return {"FINISHED"}
