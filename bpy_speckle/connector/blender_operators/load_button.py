import bpy
from typing import Set
from bpy.types import Context
from ..operations.load_operation import load_operation


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: Context, event: bpy.types.Event) -> Set[str]:
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        # Load selected model version
        load_operation(context)

        return {"FINISHED"}
