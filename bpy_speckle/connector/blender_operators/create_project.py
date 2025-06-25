import bpy
from bpy.types import Context, Event, UILayout

from specklepy.core.api.inputs import ProjectCreateInput
from specklepy.core.api.inputs.project_inputs import WorkspaceProjectCreateInput
from specklepy.core.api.enums import ProjectVisibility
from typing import Tuple, Optional

from ..utils.account_manager import _client_cache


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
            None
            if wm.selected_workspace.id == "personal"
            else wm.selected_workspace.id,
        )
        wm.selected_project_id = project_id
        wm.selected_project_name = project_name
        self.report({"INFO"}, f"Created project: {project_name} -> ID: {project_id}")
        # Force redraw
        context.window.screen = context.window.screen
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "project_name")


def register() -> None:
    bpy.utils.register_class(SPECKLE_OT_create_project)


def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_create_project)


def create_project(
    account_id: str, project_name: str, workspace_id: Optional[str]
) -> Tuple[str, str]:
    try:
        # Get cached client
        client = _client_cache.get_client(account_id)
        if not client:
            raise Exception(f"Could not get client for account: {account_id}")
        if workspace_id:
            project = client.project.create_in_workspace(
                input=WorkspaceProjectCreateInput(
                    name=project_name,
                    description="",
                    visibility=ProjectVisibility("PUBLIC"),
                    workspaceId=workspace_id,
                )
            )
        else:
            project = client.project.create(
                input=ProjectCreateInput(
                    name=project_name,
                    description="",
                    visibility=ProjectVisibility("PUBLIC"),
                )
            )

        return (project.id, project.name)
    except Exception as e:
        print(f"Failed to create project: {str(e)}")
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        raise
