import bpy
from bpy.types import Context, Event, UILayout

class SPECKLE_OT_add_project_by_url(bpy.types.Operator):
    """
    operator for adding a Speckle project by URL
    """

    bl_idname = "speckle.add_project_by_url"
    bl_label = "Add Project by URL"
    bl_description = "Add a project from a URL"

    url: bpy.props.StringProperty(  # type: ignore
        name="Project URL", description="Enter the Speckle project URL", default=""
    )

    def execute(self, context: Context) -> set[str]:
        # TODO: Implement logic to add project using the URL
        self.report({"INFO"}, f"Adding project from URL: {self.url}")
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "url", text="Speckle URL")

def register() -> None:
    bpy.utils.register_class(SPECKLE_OT_add_project_by_url)

def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_add_project_by_url)

def get_model_details_by_wrapper(wrapper: StreamWrapper) -> Tuple[str, str, str, str, str, str]:
    client = wrapper.get_client()
    client.authenticate_with_account(wrapper.get_account())
    account_id, project_id, project_name, model_id, model_name, version_id, load_option = "", "", "", "", "", "", ""
    account_id = wrapper.get_account().id
    if wrapper.stream_id:
        project_id = wrapper.stream_id
        project = client.project.get(project_id)
        project_name = project.name
    if wrapper.model_id:
        model_id = wrapper.model_id
        model = client.model.get(model_id, project_id)
        model_name = model.name
        load_option = "LATEST"
    if wrapper.commit_id:
        version_id = wrapper.commit_id
        load_option = "SPECIFIC"
    return (account_id, project_id, project_name, model_id, model_name, version_id, load_option)