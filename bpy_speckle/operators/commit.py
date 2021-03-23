'''
Commit operators
'''
import bpy,os
from bpy.props import StringProperty, BoolProperty, FloatProperty, CollectionProperty, EnumProperty

from bpy_speckle.functions import _check_speckle_client_user_stream, _create_stream, get_scale_length, _report

from bpy_speckle.convert import from_speckle_object
from bpy_speckle.clients import speckle_clients


class DeleteCommit(bpy.types.Operator):
    '''
    Delete stream
    '''
    bl_idname = "speckle.delete_commit"
    bl_label = "Delete commit"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Delete active commit permanently"

    are_you_sure: BoolProperty(
        name="Confirm",
        default=False,
        )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "are_you_sure")
        
    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            return wm.invoke_props_dialog(self)   

        return {'CANCELLED'} 

    def execute(self, context):

        if not self.are_you_sure:
            return {'CANCELLED'}

        self.are_you_sure = False

        speckle = context.scene.speckle

        check = _check_speckle_client_user_stream(context.scene)
        if check is None: return {'CANCELLED'}

        user, stream = check 
        client = speckle_clients[int(context.scene.speckle.active_user)]

        stream = user.streams[user.active_stream]
        if len(stream.branches) < 1:
            return {'CANCELLED'}
        else:
            branch = stream.branches[int(stream.branch)]
            if len(branch.commits) < 1:
                return {'CANCELLED'}
            else:
                commit = branch.commits[int(branch.commit)]

                deleted = client.commit.delete(stream_id=stream.id, commit_id=commit.id)

        return {'FINISHED'}

        bpy.ops.speckle.load_user_streams()
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}