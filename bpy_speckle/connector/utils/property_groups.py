import bpy


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
    PropertyGroup for storing object names and visibility settings
    """

    name: bpy.props.StringProperty()  # type: ignore
    hide_get: bpy.props.BoolProperty(name="Hide Get", default=False)  # type: ignore
    hide_viewport: bpy.props.BoolProperty(name="Hide Viewport", default=False)  # type: ignore
    hide_select: bpy.props.BoolProperty(name="Hide Select", default=False)  # type: ignore
    hide_render: bpy.props.BoolProperty(name="Hide Render", default=False)  # type: ignore


class speckle_collection(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing collection information and visibility settings
    """

    name: bpy.props.StringProperty()  # type: ignore
    hide_viewport: bpy.props.BoolProperty(name="Hide Viewport", default=False)  # type: ignore
    hide_select: bpy.props.BoolProperty(name="Hide Select", default=False)  # type: ignore
    hide_render: bpy.props.BoolProperty(name="Hide Render", default=False)  # type: ignore
    exclude_from_view_layer: bpy.props.BoolProperty(
        name="Exclude From View Layer", default=False
    )  # type: ignore


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
        name="Load Option", description="Option of loading the model", default=""
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
        if self.is_publish:
            return f"PUBLISH-{self.project_id}-{self.model_id}"
        else:
            return f"LOAD-{self.project_id}-{self.model_id}"
