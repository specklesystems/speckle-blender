import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event
from typing import List, Tuple
from ..utils.account_manager import get_account_enum_items
from ..utils.project_manager import get_projects_for_account

def get_accounts_callback(self, context):
    """Callback to dynamically fetch account enum items.
    """
    return get_account_enum_items()

class speckle_project(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing project information
    """

    name: bpy.props.StringProperty()  # type: ignore
    role: bpy.props.StringProperty(name="Role")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore


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
            split = row.split(factor=0.5)
            split.label(text=item.name)

            right_split = split.split(factor=0.5)
            right_split.label(text=item.role)
            right_split.label(text=item.updated)

        # handles when the list is in a grid layout
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)


class SPECKLE_OT_project_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the project selection dialog
    """

    bl_idname = "speckle.project_selection_dialog"
    bl_label = "Select Project"

    def update_projects_list(self, context: Context) -> None:
        """
        updates the list of projects based on the selected account and search query
        """
        wm = context.window_manager

        wm.selected_account_id = self.accounts

        wm.speckle_projects.clear()

        # get projects for the selected account, using search if provided
        search = self.search_query if self.search_query.strip() else None
        projects: List[Tuple[str, str, str, str]] = get_projects_for_account(
            self.accounts, search=search
        )

        for name, role, updated, id in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id

        return None

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search or Paste a URL",
        description="Search a project or paste a URL to add a project",
        default="",
        update=update_projects_list,
    )

    accounts: bpy.props.EnumProperty(  # type: ignore
        name="Account",
        description="Selected account to filter projects by",
        items=get_accounts_callback,
        update=update_projects_list
    )
    
    project_index: bpy.props.IntProperty(name="Project Index", default=0)  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.project_index < len(wm.speckle_projects):
            selected_project = wm.speckle_projects[self.project_index]

            wm.selected_project_id = selected_project.id
            wm.selected_project_name = selected_project.name

            print(f"Selected project: {selected_project.name} ({selected_project.id})")

            context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager

        wm.speckle_projects.clear()

        selected_account_id = self.accounts
        wm.selected_account_id = selected_account_id

        # Fetch projects from server
        projects: List[Tuple[str, str, str, str]] = get_projects_for_account(
            selected_account_id
        )

        for name, role, updated, id in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager
        
        # Account selection
        row = layout.row()
        if wm.selected_account_id != "NO_ACCOUNTS":
            row.prop(self, "accounts", text="")
        add_account_button_text = "Sign In" if wm.selected_account_id == "NO_ACCOUNTS" else ""
        add_account_button_icon = 'WORLD' if wm.selected_account_id == "NO_ACCOUNTS" else 'ADD'
        row.operator("speckle.add_account", icon=add_account_button_icon, text=add_account_button_text)
        
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon="VIEWZOOM", text="")
        # TODO: Add a button for adding a project by URL
        # row.operator("speckle.add_project_by_url", icon='URL', text="")

        layout.template_list(
            "SPECKLE_UL_projects_list",
            "",
            context.window_manager,
            "speckle_projects",
            self,
            "project_index",
        )
        layout.separator()


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
        layout.prop(self, "url")


def register() -> None:
    bpy.utils.register_class(speckle_project)
    bpy.utils.register_class(SPECKLE_UL_projects_list)
    bpy.utils.register_class(SPECKLE_OT_project_selection_dialog)
    bpy.utils.register_class(SPECKLE_OT_add_project_by_url)


def unregister() -> None:

    bpy.utils.unregister_class(SPECKLE_OT_add_project_by_url)
    bpy.utils.unregister_class(SPECKLE_OT_project_selection_dialog)
    bpy.utils.unregister_class(SPECKLE_UL_projects_list)
    bpy.utils.unregister_class(speckle_project)
