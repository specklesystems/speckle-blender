import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event
from typing import List, Tuple
from ..utils.account_manager import (
    get_account_enum_items,
    speckle_account,
    get_workspaces,
    speckle_workspace,
    can_create_project_in_workspace,
    get_active_workspace,
    get_default_account_id,
    get_account_from_id,
)
from ..utils.project_manager import get_projects_for_account
from ..utils.property_groups import speckle_project


class SPECKLE_UL_projects_list(bpy.types.UIList):
    """
    UIList for displaying a list of Speckle projects
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
            # enable/disable the row based on permission
            row.enabled = item.can_receive

            split = row.split(factor=0.5)
            split.label(text=item.name)

            right_split = split.split(factor=0.5)
            right_split.label(text=item.role)
            right_split.label(text=item.updated)

        # handles when the list is in a grid layout
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.enabled = item.can_receive
            layout.label(text=item.name)


class SPECKLE_OT_project_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the project selection dialog
    """

    bl_idname = "speckle.project_selection_dialog"
    bl_label = "Select Project"
    bl_description = "Select a project to load models from"

    def update_projects_list(self, context: Context) -> None:
        """
        updates the list of projects based on the selected account and search query
        """
        wm = context.window_manager


        wm.can_create_project_in_workspace = can_create_project_in_workspace(
            wm.selected_account_id, wm.selected_workspace.id
        )
        wm.speckle_projects.clear()

        # get projects for the selected account, using search if provided
        search = self.search_query if self.search_query.strip() else None
        projects: List[Tuple[str, str, str, str, bool]] = get_projects_for_account(
            wm.selected_account_id, search=search, workspace_id=wm.selected_workspace.id
        )

        for name, role, updated, id, can_receive in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            project.can_receive = can_receive
        print("Updated Projects List!")
        return None

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search or Paste a URL",
        description="Search a project or paste a URL to add a project",
        default="",
        update=update_projects_list,
    )

    project_index: bpy.props.IntProperty(name="Project Index", default=0)  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.project_index < len(wm.speckle_projects):
            selected_project = wm.speckle_projects[self.project_index]

            # verify the user has permission to receive from this project
            if not selected_project.can_receive:
                self.report(
                    {"ERROR"},
                    "Your role on this project doesn't give you permission to load.",
                )
                return {"CANCELLED"}

            wm.selected_project_id = selected_project.id
            wm.selected_project_name = selected_project.name

            print(f"Selected project: {selected_project.name} ({selected_project.id})")

            context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager

        # Clear existing projects
        wm.speckle_projects.clear()

        if wm.selected_account_id == "":
            wm.selected_account_id = get_default_account_id()

        wm.selected_workspace.id = get_active_workspace(selected_account_id)["id"]
        wm.selected_workspace.name = get_active_workspace(selected_account_id)["name"]

        # Fetch projects from server
        projects: List[Tuple[str, str, str, str, bool]] = get_projects_for_account(
            wm.selected_account_id, wm.selected_workspace.id
        )

        for name, role, updated, id, can_receive in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            project.can_receive = can_receive

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager

        # Account selection
        row = layout.row()

        if wm.selected_account_id == "NO_ACCOUNTS":
            row.operator("speckle.add_account", icon="WORLD", text="Sign In")

        # if no accounts then don't show workspaces or projects list
        if wm.selected_account_id != "NO_ACCOUNTS":
            account = get_account_from_id(wm.selected_account_id)

            row.operator(
                "speckle.account_selection_dialog",
                icon="USER",
                text=f"{account.userInfo.name} - {account.userInfo.email} - {account.serverInfo.url}",
            )
            # Workspace selection
            row = layout.row()
            row.operator(
                "speckle.workspace_selection_dialog",
                icon="WORKSPACE",
                text=wm.selected_workspace.name,
            )

            # Search field
            row = layout.row(align=True)
            row.prop(self, "search_query", icon="VIEWZOOM", text="")
            # add project by url button
            split = row.split()
            split.operator("speckle.add_project_by_url", icon="LINKED", text="")
            # create project button
            # hide if in load mode
            if wm.ui_mode != "LOAD":
                split = row.split()
                split.operator("speckle.create_project", icon="ADD", text="")
                split.enabled = wm.can_create_project_in_workspace

            layout.template_list(
                "SPECKLE_UL_projects_list",
                "",
                context.window_manager,
                "speckle_projects",
                self,
                "project_index",
            )
            layout.separator()
