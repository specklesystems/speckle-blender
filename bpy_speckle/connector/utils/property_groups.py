import bpy
from typing import Dict, Any


class speckle_project(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing project information
    """

    name: bpy.props.StringProperty()  # type: ignore
    role: bpy.props.StringProperty(name="Role")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    can_receive: bpy.props.BoolProperty(name="Can Receive", default=False)  # type: ignore


class speckle_model(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing model information
    """

    name: bpy.props.StringProperty()  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore


class speckle_version(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing version information
    """

    id: bpy.props.StringProperty(name="ID")  # type: ignore
    message: bpy.props.StringProperty(name="Message")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore
    source_app: bpy.props.StringProperty(name="Source")  # type: ignore


class speckle_object(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing model information
    """

    name: bpy.props.StringProperty()  # type: ignore


class speckle_collection(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing collection information
    """

    name: bpy.props.StringProperty()  # type: ignore


class speckle_model_card(bpy.types.PropertyGroup):
    """
    represents a Speckle model card in the Blender UI
    """

    account_id: bpy.props.StringProperty(
        name="Account ID", description="ID of the account", default=""
    )  # type: ignore
    server_url: bpy.props.StringProperty(
        name="Server URL",
        description="URL of the Server",
        default="app.speckle.systems",
    )  # type: ignore
    project_name: bpy.props.StringProperty(
        name="Project Name", description="Name of the project", default=""
    )  # type: ignore
    project_id: bpy.props.StringProperty(
        name="Project ID", description="ID of the selected project", default=""
    )  # type: ignore
    model_id: bpy.props.StringProperty(
        name="Model ID", description="ID of the model", default=""
    )  # type: ignore
    model_name: bpy.props.StringProperty(
        name="Model Name", description="Name of the model", default=""
    )  # type: ignore
    is_publish: bpy.props.BoolProperty(
        name="Publish/Load",
        description="If the model is published or loaded",
        default=False,
    )  # type: ignore
    selection_summary: bpy.props.StringProperty(
        name="Selection Summary", description="Summary of the selection", default=""
    )  # type: ignore
    version_id: bpy.props.StringProperty(
        name="Version ID", description="ID of the selected version", default=""
    )  # type: ignore
    load_option: bpy.props.StringProperty(
        name="Version ID", description="ID of the selected version", default=""
    )  # type: ignore
    objects: bpy.props.CollectionProperty(type=speckle_object)  # type: ignore
    collections: bpy.props.CollectionProperty(type=speckle_collection)  # type: ignore
    instance_loading_mode: bpy.props.StringProperty(
        name="Instance Loading Mode",
        description="Mode of loading instances",
        default="INSTANCE_PROXIES",
    )  # type: ignore
    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers to the objects",
        default=True,
    )  # type: ignore

    def get_model_card_id(self) -> str:
        if not self.project_id or not self.model_id:
            raise ValueError(
                "Project ID and Model ID are required to generate a model card ID."
            )
        return self.project_id + "-" + self.model_id

    def to_dict(self) -> Dict[str, Any]:
        """
        converts the model card to a dictionary representation
        """
        return {
            "account_id": self.account_id,
            "server_url": self.server_url,
            "project_name": self.project_name,
            "project_id": self.project_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "is_publish": self.is_publish,
            "selection_summary": self.selection_summary,
            "version_id": self.version_id,
            "objects": [obj.name for obj in self.objects],
            "collections": [col.name for col in self.collections],
            "instance_loading_mode": self.instance_loading_mode,
            "load_option": self.load_option,
            "apply_modifiers": self.apply_modifiers,
        }

    @classmethod
    def from_dict(cls, data):
        """
        creates a new model card instance from a dictionary
        """
        item = cls()
        item.account_id = data["account_id"]
        item.server_url = data["server_url"]
        item.project_name = data["project_name"]
        item.project_id = data["project_id"]
        item.model_id = data["model_id"]
        item.model_name = data["model_name"]
        item.is_publish = data["is_publish"]
        item.selection_summary = data["selection_summary"]
        item.version_id = data["version_id"]
        item.objects.clear()
        for obj_name in data.get("objects", []):
            s_obj = item.objects.add()
            s_obj.name = obj_name
        item.collections.clear()
        for col_name in data.get("collections", []):
            s_col = item.collections.add()
            s_col.name = col_name
        item.instance_loading_mode = data.get(
            "instance_loading_mode", "INSTANCE_PROXIES"
        )
        item.load_option = data.get("load_option", "LATEST")
        item.apply_modifiers = data.get("apply_modifiers", True)
