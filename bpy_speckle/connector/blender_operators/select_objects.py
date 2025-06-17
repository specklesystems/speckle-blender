from bpy.types import Operator
from bpy.props import StringProperty
from ..utils.model_card_utils import select_model_card_objects, zoom_to_selected_objects


class SPECKLE_OT_select_objects(Operator):
    """
    select all objects imported from this Speckle model
    """

    bl_idname = "speckle.select_objects"
    bl_label = "Select Objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        "Selects and zooms extents to objects loaded from this Speckle model"
    )

    model_card_id: StringProperty(
        name="Model Card ID", description="ID of the model card", default=""
    )  # type: ignore

    def execute(self, context):
        model_card = context.scene.speckle_state.get_model_card_by_id(
            self.model_card_id
        )
        if model_card is None:
            self.report({"ERROR"}, "Model card not found")
            return {"CANCELLED"}

        select_model_card_objects(model_card, context)
        zoom_to_selected_objects(context)

        self.report({"INFO"}, f"Selected {len(context.selected_objects)} objects")
        return {"FINISHED"}
