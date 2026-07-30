import bpy
from typing import List
from bpy.types import Operator, Context, Object
from bpy.props import EnumProperty
from ..utils.model_card_utils import update_model_card_objects
from ..utils.account_manager import can_create_version
from ..utils.dialog import DIALOG_WIDTH
from ..utils.misc import strip_non_renderable
from .icons import get_icon_for_type


class SPECKLE_OT_selection_filter_dialog(Operator):
    """
    operator for handling object selection and filtering
    """

    bl_idname = "speckle.selection_filter_dialog"
    bl_label = "Select Objects"
    bl_description = "Select objects to publish"

    selection_type: EnumProperty(
        name="Selection",
        items=[
            ("SELECTION", "Selection", "Select objects manually"),
        ],
        default="SELECTION",
    )  # type: ignore

    model_card_id: bpy.props.StringProperty(
        name="Model Card ID",
        description="This is used to indicate the function is called from a model card",
        default="",
    )  # type: ignore

    def execute(self, context: Context) -> set:
        wm = context.window_manager
        user_selection = context.selected_objects
        if self.model_card_id != "":
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            update_model_card_objects(model_card, user_selection)
            self.report({"INFO"}, "Selection updated")

            # On-demand permission check before publishing
            authorized, auth_message = can_create_version(
                model_card.account_id, model_card.project_id, model_card.model_id
            )
            if not authorized:
                self.report({"ERROR"}, auth_message)
                return {"CANCELLED"}

            # Call the publish operator
            bpy.ops.speckle.model_card_publish(model_card_id=self.model_card_id)

            context.area.tag_redraw()
            return {"FINISHED"}

        if not user_selection:
            # a click with nothing selected keeps the previous snapshot rather
            # than silently wiping it
            self.report({"WARNING"}, "No objects selected in the viewport")
            return {"CANCELLED"}

        wm.speckle_objects.clear()
        for sel in user_selection:
            obj = wm.speckle_objects.add()
            obj.name = sel.name
            obj.obj_type = sel.type
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: bpy.types.Event) -> set:
        # the fresh publish flow needs no input beyond the viewport selection
        # itself, so it snapshots in one click; only the model-card path opens
        # a dialog, which confirms the new selection before republishing
        if self.model_card_id == "":
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

    def draw(self, context: Context):
        layout = self.layout
        wm = context.window_manager

        project_name = wm.selected_project_name
        model_name = wm.selected_model_name
        if self.model_card_id != "":
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            project_name = model_card.project_name
            model_name = model_card.model_name

        layout.label(text=f"Project: {strip_non_renderable(project_name)}")
        layout.label(text=f"Model: {strip_non_renderable(model_name)}")

        # layout.prop(self, "selection_type")
        layout.separator()

        selected_objects: List[Object] = context.selected_objects
        total_selected: int = len(selected_objects)

        box = layout.box()
        row = box.row()
        row.label(text="Selection Summary", icon="OUTLINER_OB_GROUP_INSTANCE")
        row.label(text=f"Total: {total_selected}", icon="OBJECT_DATA")

        object_types: dict[str, int] = {}
        for obj in selected_objects:
            if obj.type not in object_types:
                object_types[obj.type] = 1
            else:
                object_types[obj.type] += 1

        col = box.column(align=True)
        for obj_type, count in object_types.items():
            row = col.row()
            row.label(text=f"{obj_type}:", icon=get_icon_for_type(obj_type))
            row.label(text=str(count))

        layout.separator()

        if self.model_card_id != "":
            layout.label(
                text="New version will be published after updating selection",
                icon="INFO_LARGE",
            )

    def check(self, context: Context) -> bool:
        return True  # this forces the dialog to redraw
