import bpy
from bpy.props import CollectionProperty, StringProperty, IntProperty, IntVectorProperty
from bpy.types import PropertyGroup

from ..ui.model_card import speckle_model_card

class SpeckleState(PropertyGroup):
    """Manages the state of the Speckle addon in Blender.

    This class stores UI-related state information for the Speckle addon, including
    the current UI mode, model cards collection, and UI interaction states.

    Attributes:
        ui_mode (StringProperty): Current UI mode of the addon. Defaults to "NONE".
        model_cards (CollectionProperty): Collection of Speckle model cards.
        model_card_index (IntProperty): Index of the currently selected model card.
        mouse_position (IntVectorProperty): 2D vector storing current mouse position.
    """
    ui_mode: StringProperty(name="UI Mode", default="NONE")  # type: ignore
    model_cards: CollectionProperty(type=speckle_model_card)  # type: ignore
    model_card_index: IntProperty(name="Model Card Index", default=0)  # type: ignore
    mouse_position: IntVectorProperty(size=2)  # type: ignore

def register() -> None:
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)  # type: ignore

def unregister() -> None:
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)
