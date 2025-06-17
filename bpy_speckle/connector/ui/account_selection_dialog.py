import bpy
from bpy.types import Context, Event
from typing import List, Tuple
from ..utils.account_manager import (
    get_account_enum_items,
    speckle_account,
    speckle_workspace,
    get_workspaces,
    get_default_workspace_id,
)
from ..utils.project_manager import get_projects_for_account
from ..ui.project_selection_dialog import speckle_project


class SPECKLE_UL_accounts_list(bpy.types.UIList):
    """
    UIList for displaying accounts
    """

    def draw_item(
        self,
        context: Context,
        layout: bpy.types.UILayout,
        data: bpy.types.PropertyGroup,
        item: bpy.types.PropertyGroup,
        icon: str,
        active_data: bpy.types.PropertyGroup,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row()
            row.label(text=item.user_name)
            row.label(text=item.server_url)
            row.label(text=item.user_email)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.user_name)


class SPECKLE_OT_account_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the account selection dialog
    """

    bl_idname = "speckle.account_selection_dialog"
    bl_label = "Select Account"
    bl_description = "Select account"

    account_index: bpy.props.IntProperty(default=0)  # type: ignore

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager
        # Clear existing accounts
        wm.speckle_accounts.clear()

        # Save selected account
        current_account_index = 0

        # Fetch accounts
        for i, (id, user_name, server_url, user_email) in enumerate(
            get_account_enum_items()
        ):
            account: speckle_account = wm.speckle_accounts.add()
            account.id = id
            account.user_name = user_name
            account.server_url = server_url
            account.user_email = user_email
            if id == wm.selected_account_id:
                current_account_index = i

        self.account_index = current_account_index
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="Select account")
        layout.template_list(
            "SPECKLE_UL_accounts_list",
            "",
            context.window_manager,
            "speckle_accounts",
            self,
            "account_index",
        )

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        # update the selected account id
        wm.selected_account_id = wm.speckle_accounts[self.account_index].id
        self.report({"INFO"}, f"Selected account: {wm.selected_account_id}")
        update_workspaces_list(context)
        update_projects_list(context)
        # redraw the area
        context.area.tag_redraw()
        return {"FINISHED"}


def update_workspaces_list(context: Context) -> None:
    wm = context.window_manager
    wm.speckle_workspaces.clear()
    workspaces = get_workspaces(wm.selected_account_id)
    for id, name in workspaces:
        workspace: speckle_workspace = wm.speckle_workspaces.add()
        workspace.id = id
        workspace.name = name
    wm.selected_workspace_id = get_default_workspace_id(wm.selected_account_id)
    print("Updated Workspaces List!")


def update_projects_list(context: Context) -> None:
    wm = context.window_manager
    wm.speckle_projects.clear()
    projects: List[Tuple[str, str, str, str, bool]] = get_projects_for_account(
        wm.selected_account_id, workspace_id=wm.selected_workspace_id
    )
    for name, role, updated, id, can_receive in projects:
        project: speckle_project = wm.speckle_projects.add()
        project.name = name
        project.role = role
        project.updated = updated
        project.id = id
        project.can_receive = can_receive
    print("Updated Projects List!")
