import bpy
from bpy.props import CollectionProperty
from bpy.types import PropertyGroup
from typing import Optional

from ..utils.property_groups import speckle_model_card


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

    def find_model_card(
        self, project_id: str, model_id: str, is_publish: bool
    ) -> Optional[speckle_model_card]:
        """Find a card by the fields that make up its identity.

        A card's id string is derived from exactly these three values
        (``get_model_card_id``); looking them up directly keeps callers from
        reassembling the id format by hand.
        """
        for model_card in self.model_cards:
            if (
                model_card.project_id == project_id
                and model_card.model_id == model_id
                and model_card.is_publish == is_publish
            ):
                return model_card
        return None


def register() -> None:
    bpy.utils.register_class(SpeckleState)
    bpy.types.Scene.speckle_state = bpy.props.PointerProperty(type=SpeckleState)  # type: ignore


def unregister() -> None:
    del bpy.types.Scene.speckle_state
    bpy.utils.unregister_class(SpeckleState)
