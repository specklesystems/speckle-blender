import bpy
from typing import Set
from bpy.types import Context
from ..operations.publish_operation import publish_operation
from ..speckle_api import can_create_version


class SPECKLE_OT_publish_model_card(bpy.types.Operator):
    bl_idname = "speckle.model_card_publish"
    bl_label = "Publish model"
    bl_description = "Publish tracked objects to Speckle"

    model_card_id: bpy.props.StringProperty(name="Model Card ID", default="")  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        # Get the model card
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )

        # On-demand permission check
        authorized, auth_message = can_create_version(
            model_card.account_id, model_card.project_id, model_card.model_id
        )
        if not authorized:
            self.report({"ERROR"}, auth_message)
            return {"CANCELLED"}

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

        if not objects_to_convert:
            self.report({"ERROR"}, "No objects to publish")
            return {"CANCELLED"}

        # publish to speckle
        success, message, version_id = publish_operation(
            context,
            model_card.account_id,
            model_card.project_id,
            model_card.model_id,
            objects_to_convert,
            apply_modifiers=model_card.apply_modifiers,
        )

        if not success:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}

        model_card.version_id = version_id
        model_card.is_publish = True

        self.report({"INFO"}, message)

        return {"FINISHED"}
