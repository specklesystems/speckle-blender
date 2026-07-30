import traceback
from typing import Set

import bpy
from bpy.types import Context
from ..utils.version_manager import get_latest_version
from ..operations.load_operation import load_operation
from ..utils.model_card_utils import (
    delete_model_card_objects,
    update_model_card_objects,
    collect_objects_with_properties,
    format_load_summary,
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

        # Resolve the version before the scene is touched. A load failure is
        # only knowable after the attempt, so it costs the previous objects
        # (see the delete note below), but a missing latest version is knowable
        # up front — look it up first and the card keeps its geometry when
        # there is nothing to load.
        if model_card.load_option == "LATEST":
            latest_version = get_latest_version(
                model_card.account_id, model_card.project_id, model_card.model_id
            )
            if latest_version is None:
                self.report(
                    {"ERROR"},
                    f"Could not fetch latest version for model '{model_card.model_name}'",
                )
                return {"CANCELLED"}
            version_id = latest_version[0]
        else:
            version_id = model_card.version_id

        old_properties = collect_objects_with_properties(model_card)
        # The delete has to precede the load: the replacements carry the same
        # applicationIds, and delete_model_card_objects resolves by
        # applicationId. Clear the card's lists to match, so a failed load
        # below does not leave it referencing deleted data-blocks.
        delete_model_card_objects(model_card, context)
        model_card.objects.clear()
        model_card.collections.clear()

        # set wm
        wm.selected_account_id = model_card.account_id
        wm.selected_project_id = model_card.project_id
        wm.selected_model_name = model_card.model_name

        # A bundle version that fails to read raises by design, so guard the
        # load and leave model_card.version_id untouched until it succeeds.
        # The finally clears the window manager on every exit path.
        try:
            wm.selected_version_id = version_id

            converted_objects = load_operation(
                context, model_card.instance_loading_mode
            )
        except Exception as e:
            traceback.print_exc()
            self.report({"ERROR"}, f"Load failed: {e}")
            return {"CANCELLED"}
        finally:
            # Clear selected model details from Window Manager
            wm.selected_account_id = ""
            wm.selected_project_id = ""
            wm.selected_version_id = ""
            wm.selected_model_name = ""

        # update model card details
        update_model_card_objects(model_card, converted_objects, old_properties)
        model_card.version_id = version_id

        self.report({"INFO"}, format_load_summary(model_card))

        return {"FINISHED"}
