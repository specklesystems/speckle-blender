import bpy
from bpy.props import CollectionProperty, StringProperty, IntProperty, IntVectorProperty, EnumProperty

from ..ui.project_selection_dialog import speckle_project
from ..ui.model_selection_dialog import speckle_model
from ..ui.version_selection_dialog import speckle_version
from ..ui.model_card import speckle_model_card

class SpeckleState(bpy.types.PropertyGroup):    
    projects: CollectionProperty(type=speckle_project)
    models: CollectionProperty(type=speckle_model)
    versions: CollectionProperty(type=speckle_version)
    ui_mode: StringProperty(name="UI Mode", default="NONE")
    model_cards: CollectionProperty(type=speckle_model_card)
    model_card_index: IntProperty(name="Model Card Index", default=0)
    mouse_position: IntVectorProperty(size=2)

    # Account
    account: EnumProperty(
        name="Account", 
        description= "Selected account to filter projects by",
        items= [("account1", "Account 1", "Account 1"), ("account2", "Account 2", "Account 2")],
        default="account1",)

def register():
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)

def unregister():
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)