'''
Object UI elements
'''

import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, CollectionProperty, EnumProperty

class OBJECT_PT_speckle(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    #bl_idname = 'OBJECT_PT_speckle'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_label = "Speckle"

    def draw_header(self, context):
        self.layout.prop(context.object.speckle, "enabled", text="")

    def draw(self, context):
        ob = context.object
        layout = self.layout
        layout.active = ob.speckle.enabled
        col = layout.column()
        col.prop(ob.speckle, "send_or_receive", expand=True)
        col.prop(ob.speckle, "stream_id", text="Stream ID")
        col.prop(ob.speckle, "object_id", text="Object ID")
        col.operator("speckle.update_object", text='Update')
        col.operator("speckle.reset_object", text='Reset')
        col.operator("speckle.delete_object", text='Delete')