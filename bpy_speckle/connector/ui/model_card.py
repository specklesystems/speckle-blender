import bpy
from typing import Dict, Any
class speckle_model_card(bpy.types.PropertyGroup):
    """Represents a Speckle model card in the Blender UI.

    This class stores information about a Speckle model, including its project name,
    whether if its publish or load, and version information. It is used to display and manage model
    cards in the Blender interface.

    Attributes:
        project_name (StringProperty): Name of the project containing the model.
        model_name (StringProperty): Name of the Speckle model.
        is_publish (BoolProperty): Flag indicating if the model is being published (True) or loaded (False).
        selection_summary (StringProperty): Summary text of the current object selection.
        version_id (StringProperty): Unique identifier of the selected version.
    """
    account_id: bpy.props.StringProperty(name="Server URL", description="URL of the Server", default="app.speckle.systems")  # type: ignore
    server_url: bpy.props.StringProperty(name="Server URL", description="URL of the Server", default="app.speckle.systems")  # type: ignore
    project_name: bpy.props.StringProperty(name="Project Name", description="Name of the project", default="")  # type: ignore
    project_id: bpy.props.StringProperty(name="Project ID", description="ID of the selected project", default="") # type: ignore
    model_id: bpy.props.StringProperty(name="Model ID", description="ID of the model", default="") # type: ignore
    model_name: bpy.props.StringProperty(name="Model Name", description="Name of the model", default="")  # type: ignore
    is_publish: bpy.props.BoolProperty(name="Publish/Load", description="If the model is published or loaded", default=False)  # type: ignore
    selection_summary: bpy.props.StringProperty(name="Selection Summary", description="Summary of the selection", default="")  # type: ignore
    version_id: bpy.props.StringProperty(name="Version ID", description="ID of the selected version", default="")  # type: ignore
    load_option: bpy.props.StringProperty(name="Version ID", description="ID of the selected version", default="")  # type: ignore

    def to_dict(self) -> Dict[str, Any]:
        """Converts the model card to a dictionary representation.

        Returns:
            dict: A dictionary containing all model card properties with their current values.
        """
        return {
            "server_url": self.server_url,
            "project_name": self.project_name,
            "project_id": self.project_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "is_publish": self.is_publish,
            "selection_summary": self.selection_summary,
            "version_id": self.version_id,
        }
    
    @classmethod
    def from_dict(cls, data):
        """Creates a new model card instance from a dictionary.

        Args:
            data (dict): Dictionary containing model card properties and their values.

        Returns:
            speckle_model_card: A new instance of the model card with properties set from the dictionary.
        """
        item = cls()
        item.server_url = data["server_url"]
        item.project_name = data["project_name"]
        item.project_id = data["project_id"]
        item.model_id = data["model_id"]
        item.model_name = data["model_name"]
        item.is_publish = data["is_publish"]
        item.selection_summary = data["selection_summary"]
        item.version_id = data["version_id"]
        