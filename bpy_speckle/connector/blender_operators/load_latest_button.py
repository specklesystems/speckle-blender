import bpy
from typing import Set
from bpy.types import Context
from ..utils.version_manager import get_latest_version
from ..operations.load_operation import load_operation


class SPECKLE_OT_load_latest(bpy.types.Operator):
    bl_idname = "speckle.load_latest"
    bl_label = "Load Latest from Speckle"
    bl_description = "Load the latest version from Speckle"

    model_card_id: bpy.props.StringProperty(name="Model Card ID", default="")  # type: ignore

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        # Get the model card
        model_card = context.scene.speckle_state.get_model_card_by_id(self.model_card_id)

        # Check if load_option is set to "LATEST"
        if model_card.load_option != "LATEST":
            # Do nothing if load_option is not "LATEST"
            return {"FINISHED"}
        
        # Get the latest version from Speckle
        latest_version_id, message, timestamp = get_latest_version(
            model_card.account_id, 
            model_card.project_id, 
            model_card.model_id
        )
        # Throw error if latest version is not found
        if not latest_version_id:
            self.report({"ERROR"}, "Failed to get latest version")
            return {"CANCELLED"}
        
        # Check if the collection exists and delete it if it does
        collection = bpy.data.collections.get(model_card.collection_name)
        
        # Update the model card with the latest version ID
        original_version_id = model_card.version_id
        if latest_version_id == original_version_id:
            self.report({"INFO"}, "Latest version is already loaded")
            return {"FINISHED"}

        if collection:
            # Remove the collection
            bpy.data.collections.remove(collection)
            self.report({"INFO"}, f"Deleted existing collection: {model_card.collection_name}")
        # overwrite version id of the model card stored in the doc
        model_card.version_id = latest_version_id
        
        # overwrite version id store in wm
        # Set Window Manager properties 
        wm.selected_account_id = model_card.account_id
        wm.selected_project_id = model_card.project_id
        wm.selected_model_name = model_card.model_name
        wm.selected_version_id = latest_version_id
        
        # Load the latest version
        try:
            load_operation(context)
            self.report(
                {"INFO"}, 
                f"Loaded latest version: {latest_version_id[:8]} (was: {original_version_id[:8]})"
            )
            # update collection name in model card
            model_card.collection_name = f"{model_card.model_name} - {latest_version_id[:8]}"
        except Exception as e:
            # Restore the original version ID if loading fails
            model_card.version_id = original_version_id
            self.report({"ERROR"}, f"Failed to load latest version: {str(e)}")
            return {"CANCELLED"}
        
        # Clear selected model details from Window Manager
        wm.selected_account_id = ""
        wm.selected_project_id = ""
        wm.selected_version_id = ""
        wm.selected_model_name = ""
        
        return {"FINISHED"}