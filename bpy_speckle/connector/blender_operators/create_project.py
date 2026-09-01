import bpy
from bpy.types import Context, Event, UILayout

from ..speckle_api import create_project
from ..utils.dialog import DIALOG_WIDTH


class SPECKLE_OT_create_project(bpy.types.Operator):
    """
    operator for adding a Speckle project by URL
    """

    bl_idname = "speckle.create_project"
    bl_label = "Create Project"
    bl_description = "Create a new Speckle project"

    project_name: bpy.props.StringProperty(name="Project Name")  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        project_id, project_name = create_project(
            wm.selected_account_id,
            self.project_name,
            wm.selected_workspace.id,
        )
        wm.selected_project_id = project_id
        wm.selected_project_name = project_name
        self.report({"INFO"}, f"Created project: {project_name} -> ID: {project_id}")
        # Force redraw
        context.window.screen = context.window.screen
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "project_name")
