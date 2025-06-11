import bpy
from typing import Set
from bpy.types import Context, Event
from ..operations.load_operation import load_operation
from ..utils.account_manager import get_server_url_by_account_id


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    instance_loading_mode: bpy.props.EnumProperty(  # type: ignore
        name="Instance Loading",
        description="Choose how to load instances",
        items=[
            ("INSTANCE_PROXIES", "Collection Instances", "Load objects as collection instances"),
            ("LINKED_DUPLICATES", "Linked Duplicates", "Get objects as linked duplicates"),
        ],
        default="INSTANCE_PROXIES",
    )

    def draw(self, context: Context) -> None:
        layout = self.layout
        split = layout.split(factor=0.4)
        split.label(text="Instance Loading:")
        split.prop(self, "instance_loading_mode", text="")

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager
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
        model_card.collection_name = f"{wm.selected_model_name} - {wm.selected_version_id[:8]}"

        load_operation(context, self.instance_loading_mode)

        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_project_name = ""
        wm.selected_model_id = ""
        wm.selected_model_name = ""
        wm.selected_version_load_option = ""
        wm.selected_version_id = ""

        return {"FINISHED"}
