import bpy

class MousePositionMixin:
    original_mouse_position: bpy.props.IntVectorProperty(size=2)
    mouse_snap: bpy.props.BoolProperty(name="Mouse Snap", default=False)

    def init_mouse_position(self, context, event):
        self.original_mouse_position = (event.mouse_x, event.mouse_y)
        self.mouse_snap = False
        context.window.cursor_warp(context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1])

    def restore_mouse_position(self, context):
        if not self.mouse_snap:
            self.mouse_snap = True
            context.window.cursor_warp(self.original_mouse_position[0], self.original_mouse_position[1])