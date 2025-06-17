import bpy
from typing import List
from bpy.types import Operator, Context, Object
from bpy.props import EnumProperty
from ..utils.model_card_utils import update_model_card_objects


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

    version_message: bpy.props.StringProperty(
        name="Version Message",
        description="Message to be used for the version",
        default="",
    )  # type: ignore

    def execute(self, context: Context) -> set:
        wm = context.window_manager
        wm.speckle_objects.clear()
        user_selection = context.selected_objects
        if self.model_card_id != "":
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            update_model_card_objects(model_card, user_selection)
            self.report({"INFO"}, "Selection updated")

            # Call the publish operator
            bpy.ops.speckle.model_card_publish(
                model_card_id=self.model_card_id, version_message=self.version_message
            )

            context.area.tag_redraw()
            return {"FINISHED"}

        for sel in user_selection:
            obj = wm.speckle_objects.add()
            obj.name = sel.name
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: bpy.types.Event) -> set:
        return context.window_manager.invoke_props_dialog(self)

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

        layout.label(text=f"Project: {project_name}")
        layout.label(text=f"Model: {model_name}")

        #layout.prop(self, "selection_type")
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
            row.label(text=f"{obj_type}:", icon=self.get_icon_for_type(obj_type))
            row.label(text=str(count))

        layout.separator()

        if self.model_card_id != "":
            layout.label(text="Version Message")
            layout.prop(self, "version_message", text="")
            layout.label(
                text="New version will be published after updating selection",
                icon="INFO_LARGE",
            )

    def get_icon_for_type(self, obj_type: str) -> str:
        icon_map: dict[str, str] = {
            "MESH": "OUTLINER_OB_MESH",
            "CURVE": "OUTLINER_OB_CURVE",
            "SURFACE": "OUTLINER_OB_SURFACE",
            "META": "OUTLINER_OB_META",
            "FONT": "OUTLINER_OB_FONT",
            "ARMATURE": "OUTLINER_OB_ARMATURE",
            "LATTICE": "OUTLINER_OB_LATTICE",
            "EMPTY": "OUTLINER_OB_EMPTY",
            "GPENCIL": "OUTLINER_OB_GREASEPENCIL",
            "CAMERA": "OUTLINER_OB_CAMERA",
            "LIGHT": "OUTLINER_OB_LIGHT",
            "SPEAKER": "OUTLINER_OB_SPEAKER",
            "LIGHT_PROBE": "OUTLINER_OB_LIGHTPROBE",
        }
        return icon_map.get(obj_type, "OBJECT_DATA")

    def check(self, context: Context) -> bool:
        return True  # this forces the dialog to redraw
