import bpy
from typing import Set
from bpy.types import Context, Event
from ..operations.publish_operation import publish_operation


class SPECKLE_OT_publish_model_card(bpy.types.Operator):
    bl_idname = "speckle.model_card_publish"
    bl_label = "Publish model"
    bl_description = "Publish model"

    model_card_id: bpy.props.StringProperty(name="Model Card ID", default="")  # type: ignore
    version_message: bpy.props.StringProperty(name="Version Message", default="")  # type: ignore

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.prop(self, "version_message")

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        # Get the model card
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        # set wm
        wm.selected_account_id = model_card.account_id
        wm.selected_project_id = model_card.project_id
        wm.selected_model_id = model_card.model_id

        # get model card objects
        objects_to_convert = []
        for speckle_obj in model_card.objects:
            blender_obj = bpy.data.objects.get(speckle_obj.name)
            if blender_obj:
                objects_to_convert.append(blender_obj)
            else:
                self.report(
                    {"WARNING"}, f"Object '{speckle_obj.name}' not found, skipping"
                )

        # publish to speckle
        success, message, version_id = publish_operation(
            context,
            objects_to_convert,
            self.version_message,
            model_card.apply_modifiers,
        )

        if not success:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_model_id = ""

        self.report({"INFO"}, message)

        return {"FINISHED"}
