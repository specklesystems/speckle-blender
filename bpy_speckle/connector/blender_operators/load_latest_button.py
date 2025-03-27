import bpy
from typing import Set, Tuple
from bpy.types import Context
from ..utils.version_manager import get_latest_version
from ..operations.load_operation import load_operation


class SPECKLE_OT_load_latest(bpy.types.Operator):
    bl_idname = "speckle.load_latest"
    bl_label = "Load Latest from Speckle"
    bl_description = "Load the latest version from Speckle"

    model_card_index: bpy.props.IntProperty(default=0)

    def execute(self, context: Context) -> Set[str]:
        # Get the model card from the scene
        model_cards = context.scene.speckle_state.model_cards
        if not model_cards or self.model_card_index >= len(model_cards):
            self.report({"ERROR"}, "Invalid model card index")
            return {"CANCELLED"}

        model_card = model_cards[self.model_card_index]
        
        # Check if load_option is set to "LATEST"
        if model_card.load_option != "LATEST":
            # Do nothing if load_option is not "LATEST"
            return {"FINISHED"}
        
        # Construct the collection name
        collection_name = f"{model_card.model_name} - {model_card.version_id[:8]}"
        
        # Check if the collection exists and delete it if it does
        collection = bpy.data.collections.get(collection_name)
        if collection:
            # Remove the collection
            bpy.data.collections.remove(collection)
            self.report({"INFO"}, f"Deleted existing collection: {collection_name}")
        
        # Get the latest version from Speckle
        latest_version_id, message, timestamp = get_latest_version(
            model_card.account_id, 
            model_card.project_id, 
            model_card.model_id
        )
        
        if not latest_version_id:
            self.report({"ERROR"}, "Failed to get latest version")
            return {"CANCELLED"}
        
        # Update the model card with the latest version ID
        original_version_id = model_card.version_id
        model_card.version_id = latest_version_id
        
        # Load the latest version
        try:
            load_operation(context, model_card)
            self.report(
                {"INFO"}, 
                f"Loaded latest version: {latest_version_id[:8]} (was: {original_version_id[:8]})"
            )
        except Exception as e:
            # Restore the original version ID if loading fails
            model_card.version_id = original_version_id
            self.report({"ERROR"}, f"Failed to load latest version: {str(e)}")
            return {"CANCELLED"}
        
        return {"FINISHED"}