import bpy
from bpy.types import Context, UILayout, Event, PropertyGroup
from typing import List, Tuple
from ..utils.account_manager import get_workspaces, speckle_workspace


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
        if wm.selected_workspace_id:
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
            context.area.tag_redraw()
        return {"FINISHED"}
