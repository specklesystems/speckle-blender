import bpy
from bpy.types import Context, UILayout, Event, PropertyGroup
from typing import List, Tuple
from ..utils.account_manager import get_workspaces, speckle_workspace
from ..utils.project_manager import get_projects_for_account
from ..utils.account_manager import can_create_project_in_workspace


class SPECKLE_UL_workspaces_list(bpy.types.UIList):
    """
    UIList for workspaces
    """

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: str,
        active_data: PropertyGroup,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.label(text=item.name)

        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)


class SPECKLE_OT_workspace_selection_dialog(bpy.types.Operator):
    """
    Operator for selecting a workspace
    """

    bl_idname = "speckle.workspace_selection_dialog"
    bl_label = "Select Workspace"
    bl_description = "Select a workspace to load projects from"

    workspace_index: bpy.props.IntProperty(name="Workspace Index", default=0)  # type: ignore

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager
        wm.speckle_workspaces.clear()
        workspaces: List[Tuple[str, str]] = get_workspaces(wm.selected_account_id)
        current_workspace_index = 0
        for i, (id, name) in enumerate(workspaces):
            workspace: speckle_workspace = wm.speckle_workspaces.add()
            workspace.id = id
            workspace.name = name
            if id == wm.selected_workspace_id:
                current_workspace_index = i
        self.workspace_index = current_workspace_index
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager
        layout.label(text=f"Selected Workspace: {wm.selected_workspace_name}")
        layout.template_list(
            "SPECKLE_UL_workspaces_list",
            "",
            context.window_manager,
            "speckle_workspaces",
            self,
            "workspace_index",
        )

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.workspace_index < len(wm.speckle_workspaces):
            selected_workspace = wm.speckle_workspaces[self.workspace_index]
            wm.selected_workspace_id = selected_workspace.id
            wm.selected_workspace_name = selected_workspace.name
            update_projects_list(context)
            context.area.tag_redraw()
        return {"FINISHED"}


def update_projects_list(context):
    """Update projects list when workspace changes"""

    wm = context.window_manager
    wm.speckle_projects.clear()

    # get projects for the selected account and workspace
    projects = get_projects_for_account(
        wm.selected_account_id, wm.selected_workspace_id
    )

    for name, role, updated, id, can_receive in projects:
        project = wm.speckle_projects.add()
        project.name = name
        project.role = role
        project.updated = updated
        project.id = id
        project.can_receive = can_receive

    # Update can_create_project_in_workspace flag
    wm.can_create_project_in_workspace = can_create_project_in_workspace(
        wm.selected_account_id, wm.selected_workspace_id
    )
    print(f"Workspace changed to: {wm.selected_workspace_id}")
    print("Projects list updated")

    context.area.tag_redraw()
