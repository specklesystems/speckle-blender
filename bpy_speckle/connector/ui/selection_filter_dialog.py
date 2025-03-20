"""Module for handling object selection filtering.

This module provides the UI components and functionality for filtering and selecting
Blender objects for publishing to Speckle.
"""

import bpy
from typing import List
from .mouse_position_mixin import MousePositionMixin
from bpy.types import Operator, Context, Object
from bpy.props import EnumProperty, StringProperty

class SPECKLE_OT_selection_filter_dialog(MousePositionMixin, Operator):
    """Operator for handling object selection and filtering.

    This operator manages the UI and functionality for selecting and filtering
    Blender objects before publishing to Speckle, including selection type options
    and selection summary display.

    Attributes:
        selection_type: The type of selection method to use.
        project_name: The name of the selected project.
        project_id: The ID of the selected project.
        model_name: The name of the selected model.
        model_id: The ID of the selected model.
    """
    bl_idname = "speckle.selection_filter_dialog"
    bl_label = "Select Objects"

    selection_type: EnumProperty(
        name="Selection",
        items=[
            ("SELECTION", "Selection", "Select objects manually"),
        ],
        default="SELECTION"
    ) # type: ignore

    project_name: StringProperty(
        name="Project Name",
        description="Name of the selected project",
        default=""
    ) # type: ignore

    project_id: StringProperty(
        name="Project ID",
        description="ID of the selected project",
        default=""
    ) # type: ignore

    model_name: StringProperty(
        name="Model Name",
        description="Name of the selected model",
        default=""
    ) # type: ignore

    model_id: StringProperty(
        name="Model ID",
        description="ID of the selected model",
        default=""
    ) # type: ignore

    def execute(self, context: Context) -> set:
        model_card = context.scene.speckle_state.model_cards.add()
        model_card.project_name = self.project_name
        model_card.model_name = self.model_name
        model_card.model_id = self.model_id
        model_card.project_id = self.project_id
        model_card.is_publish = True

        # Create the selection summary
        selected_objects: list[Object] = context.selected_objects
        total_selected: int = len(selected_objects)
        object_types: dict[str, int] = {}
        for obj in selected_objects:
            if obj.type not in object_types:
                object_types[obj.type] = 1
            else:
                object_types[obj.type] += 1

        summary: str = f"{total_selected} objects - "
        for obj_type, count in object_types.items():
            summary += f"{obj_type}: {count}, "

        model_card.selection_summary = summary.strip()
        return {'FINISHED'}

    def invoke(self, context: Context, event: bpy.types.Event) -> set:
        # Initialize mouse position
        self.init_mouse_position(context, event)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        layout = self.layout

        layout.label(text=f"Project: {self.project_name}")
        layout.label(text=f"Model: {self.model_name}")

        # Selection dropdown
        layout.prop(self, "selection_type")
        layout.separator()

        # Get selected objects
        selected_objects: List[Object] = context.selected_objects
        total_selected: int = len(selected_objects)

        # Create a box for the selection summary
        box = layout.box()
        row = box.row()
        row.label(text="Selection Summary", icon='OUTLINER_OB_GROUP_INSTANCE')
        row.label(text=f"Total: {total_selected}", icon='OBJECT_DATA')

        # Display object types and counts
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

        # Restore mouse position
        self.restore_mouse_position(context)
    def get_icon_for_type(self, obj_type: str) -> str:
        icon_map: dict[str, str] = {
            'MESH': 'OUTLINER_OB_MESH',
            'CURVE': 'OUTLINER_OB_CURVE',
            'SURFACE': 'OUTLINER_OB_SURFACE',
            'META': 'OUTLINER_OB_META',
            'FONT': 'OUTLINER_OB_FONT',
            'ARMATURE': 'OUTLINER_OB_ARMATURE',
            'LATTICE': 'OUTLINER_OB_LATTICE',
            'EMPTY': 'OUTLINER_OB_EMPTY',
            'GPENCIL': 'OUTLINER_OB_GREASEPENCIL',
            'CAMERA': 'OUTLINER_OB_CAMERA',
            'LIGHT': 'OUTLINER_OB_LIGHT',
            'SPEAKER': 'OUTLINER_OB_SPEAKER',
            'LIGHT_PROBE': 'OUTLINER_OB_LIGHTPROBE',
        }
        return icon_map.get(obj_type, 'OBJECT_DATA')

    def check(self, context: Context) -> bool:
        return True  # This forces the dialog to redraw
