import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy.types import PropertyGroup
from typing import Optional

from ..ui.model_card import speckle_model_card


class SpeckleState(PropertyGroup):
    """
    manages the state of the Speckle addon in Blender
    """

    model_cards: CollectionProperty(type=speckle_model_card)  # type: ignore

    def get_model_card_by_id(self, model_card_id: str) -> Optional[speckle_model_card]:
        """Find a model card by its ID."""
        for model_card in self.model_cards:
            if model_card.get_model_card_id() == model_card_id:
                return model_card
        return None


def register() -> None:
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)  # type: ignore


def unregister() -> None:
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)
