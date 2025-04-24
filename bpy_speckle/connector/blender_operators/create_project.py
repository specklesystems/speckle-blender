import bpy
from bpy.types import Context, Event, UILayout
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts
from specklepy.core.api.credentials import Account
from specklepy.core.api.inputs import ProjectCreateInput
from specklepy.core.api.enums import ProjectVisibility
from typing import List, Tuple, Optional
from ..utils.misc import get_blender_filename

class SPECKLE_OT_create_project(bpy.types.Operator):
    """
    operator for adding a Speckle project by URL
    """

    bl_idname = "speckle.create_project"
    bl_label = "Create Project"
    bl_description = "Create a new Speckle project"

    project_name: bpy.props.StringProperty(name="Project Name")

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        project_id, project_name = create_project(
            wm.selected_account_id, self.project_name
        )
        wm.selected_project_id = project_id
        wm.selected_project_name = project_name
        self.report({'INFO'}, f"Created project: {project_name} -> ID: {project_id}")
        # Force redraw
        context.window.screen = context.window.screen
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "project_name", placeholder=get_blender_filename())

def register() -> None:
    bpy.utils.register_class(SPECKLE_OT_create_project)

def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_create_project)

def create_project(account_id: str, project_name: str) -> Tuple[str, str]:
    accounts: List[Account] = get_local_accounts()
    account: Optional[Account] = next(
            (acc for acc in accounts if acc.id == account_id), None
        )

    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)

    project = client.project.create(input=ProjectCreateInput(name=project_name, description="", visibility = ProjectVisibility("PUBLIC")))
    return [project.id, project.name]
