import bpy
from typing import Set
from bpy.types import Context, Event
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

    instance_loading_mode: bpy.props.EnumProperty(  # type: ignore
        name="Instance Loading",
        description="Choose how to load instances",
        items=[
            (
                "INSTANCE_PROXIES",
                "Collection Instances",
                "Load objects as collection instances",
            ),
            (
                "LINKED_DUPLICATES",
                "Linked Duplicates",
                "Get objects as linked duplicates",
            ),
        ],
        default="INSTANCE_PROXIES",
    )

    def draw(self, context: Context) -> None:
        layout = self.layout
        row = layout.row()
        row.label(text="Instance Loading:")
        row.prop(self, "instance_loading_mode", text="")

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self)

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
        model_card.instance_loading_mode = self.instance_loading_mode

        converted_objects = load_operation(context, self.instance_loading_mode)
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
