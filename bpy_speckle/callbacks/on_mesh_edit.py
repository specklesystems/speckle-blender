import bpy
from bpy.app.handlers import persistent


@persistent
def scb_on_mesh_edit(context):
    """
    DEPRECATED
    Do something whenever a mesh is updated
    """
    edit_obj = bpy.context.edit_object
    if edit_obj is not None and edit_obj.is_updated_data is True:
        print("Mesh edited: {}".format(edit_obj))
    #print('>>> Update')
