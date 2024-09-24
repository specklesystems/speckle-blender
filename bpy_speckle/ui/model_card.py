import bpy

class speckle_model_card(bpy.types.PropertyGroup):
    project_name: bpy.props.StringProperty(name="Project Name", description="Name of the project", default="")
    model_name: bpy.props.StringProperty(name="Model Name", description="Name of the model", default="")
    is_publish: bpy.props.BoolProperty(name="Publish/Load", description="If the model is published or loaded", default=False)
    selection_summary: bpy.props.StringProperty(name="Selection Summary", description="Summary of the selection", default="")
    version_id: bpy.props.StringProperty(name="Version ID", description="ID of the selected version", default="")