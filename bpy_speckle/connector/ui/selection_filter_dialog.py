import bpy
from typing import List
from bpy.types import Operator, Context, Object
from bpy.props import EnumProperty


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


    def execute(self, context: Context) -> set:
        # model_card = context.scene.speckle_state.model_cards.add()
        # model_card.project_name = self.project_name
        # model_card.model_name = self.model_name
        # model_card.model_id = self.model_id
        # model_card.project_id = self.project_id
        # model_card.is_publish = True

        # selected_objects: list[Object] = context.selected_objects
        # total_selected: int = len(selected_objects)
        # object_types: dict[str, int] = {}
        # for obj in selected_objects:
        #     if obj.type not in object_types:
        #         object_types[obj.type] = 1
        #     else:
        #         object_types[obj.type] += 1

        # summary: str = f"{total_selected} objects - "
        # for obj_type, count in object_types.items():
        #     summary += f"{obj_type}: {count}, "

        # model_card.selection_summary = summary.strip()
        #TODO: implement selection filter dialog
        wm = context.window_manager
        wm.speckle_objects.clear()
        user_selection = context.selected_objects
        for sel in user_selection:
            obj = wm.speckle_objects.add()
            obj.name = sel.name
        return {"FINISHED"}

    def invoke(self, context: Context, event: bpy.types.Event) -> set:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        layout = self.layout
        wm = context.window_manager

        layout.label(text=f"Project: {wm.selected_project_name}")
        layout.label(text=f"Model: {wm.selected_model_name}")

        layout.prop(self, "selection_type")
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

class speckle_object(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing model information
    """

    name: bpy.props.StringProperty()  #type: ignore
