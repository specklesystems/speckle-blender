import bpy

class SPECKLE_OT_selection_dialog(bpy.types.Operator):
    bl_idname = "speckle.selection_dialog"
    bl_label = "Select Objects"

    selection_type: bpy.props.EnumProperty(
        name="Selection Type",
        items=[
            ("SELECTION", "Selection", "Select objects manually"),
        ],
        default="SELECTION"
    )
    

    def execute(self, context):
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selection_type")
        layout.separator()

        # Get selected objects
        selected_objects = context.selected_objects
        
        # Display selection summary
        layout.label(text=f"Selected {len(selected_objects)} objects.")

        object_types = {}
        for obj in selected_objects:
            if obj.type not in object_types:
                object_types[obj.type] = 1
            else:
                object_types[obj.type] += 1
        
        for obj_type, count in object_types.items():
            layout.label(text=f"- {obj_type}: {count}")

    
    def check(self, context):
        return True  # This forces the dialog to redraw

