import bpy

class speckle_model_card(bpy.types.PropertyGroup):
    project_name: bpy.props.StringProperty(name="Project Name", description="Name of the project", default="")
    model_name: bpy.props.StringProperty(name="Model Name", description="Name of the model", default="")
    is_publish: bpy.props.BoolProperty(name="Publish/Load", description="If the model is published or loaded", default=False)
    selection_summary: bpy.props.StringProperty(name="Selection Summary", description="Summary of the selection", default="")
    version_id: bpy.props.StringProperty(name="Version ID", description="ID of the selected version", default="")

    def to_dict(self):
        return{
            "project_name" : self.project_name,
            "model_name" : self.model_name,
            "is_publish" : self.is_publish,
            "selection_summary" : self.selection_summary,
            "version_id" : self.version_id,
        }
    
    @classmethod
    def from_dict(cls, data):
        item = cls()
        item.project_name = data["project_name"]
        item.model_name = data["model_name"]
        item.is_publish = data["is_publish"]
        item.selection_summary = data["selection_summary"]
        item.version_id = data["version_id"]
        