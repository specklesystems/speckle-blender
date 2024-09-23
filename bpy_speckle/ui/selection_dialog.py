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
        total_selected = len(selected_objects)

        # Create a box for the selection summary
        box = layout.box()
        row = box.row()
        row.label(text="Selection Summary", icon='OUTLINER_OB_GROUP_INSTANCE')
        row.label(text=f"Total: {total_selected}", icon='OBJECT_DATA')
        
        # Display object types and counts

        object_types = {}
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
    
    def get_icon_for_type(self, obj_type):
        icon_map = {
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
    
    def check(self, context):
        return True  # This forces the dialog to redraw

