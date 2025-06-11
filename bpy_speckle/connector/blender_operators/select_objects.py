import bpy
from bpy.types import Operator
from bpy.props import StringProperty


class SPECKLE_OT_select_objects(Operator):
    """
    select all objects imported from this Speckle model
    """

    bl_idname = "speckle.select_objects"
    bl_label = "Select Objects"
    bl_options = {"REGISTER", "UNDO"}

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

        # deselect all objects first
        bpy.ops.object.select_all(action="DESELECT")

        # select objects in model card
        for obj in model_card.objects:
            blender_obj = bpy.data.objects.get(obj.name)
            if not blender_obj:
                continue
            blender_obj.select_set(True)

        selected = context.selected_objects
        if selected:
            context.view_layer.objects.active = selected[0]

            bpy.ops.view3d.view_selected()

        self.report({"INFO"}, f"Selected {len(context.selected_objects)} objects")
        return {"FINISHED"}
