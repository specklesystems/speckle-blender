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
    