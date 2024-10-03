import bpy
from .bindings.account_binding import AccountBinding

class SpeckleState(bpy.types.PropertyGroup):
    account_binding: bpy.props.PointerProperty(type=AccountBinding)

    def initialize(self):
        if not self.account_binding:
            self.account_binding.get_local_accounts()

def register():
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)

def unregister():
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)
