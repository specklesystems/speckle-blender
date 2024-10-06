import bpy
from bpy.props import CollectionProperty, StringProperty, IntProperty, IntVectorProperty, EnumProperty

from ..ui.project_selection_dialog import speckle_project
from ..ui.model_selection_dialog import speckle_model
from ..ui.version_selection_dialog import speckle_version
from ..ui.model_card import speckle_model_card

from specklepy.logging.exceptions import SpeckleException
from specklepy.api.credentials import get_local_accounts

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
        items= lambda self, context: get_account_enum_items(),
        default=None)

def get_account_enum_items():
    try:
        accounts = get_local_accounts()
        return [
            (
            account.id,
            f"{account.userInfo.name} - {account.userInfo.email} - {account.serverInfo.url}", 
            f"{account.userInfo.name} - {account.userInfo.email} - {account.serverInfo.url}"
            )
            for account in accounts
        ]
    except SpeckleException as e:
        print(f"Error fetching Speckle accounts: {e}")
        return [("", "No accounts found", "")]

def register():
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)

def unregister():
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)