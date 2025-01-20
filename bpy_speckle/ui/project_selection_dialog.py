import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event, WindowManager
from typing import List, Tuple
from ..utils.account_manager import get_account_enum_items, get_default_account_id
from ..utils.project_manager import get_projects_for_account

class speckle_project(bpy.types.PropertyGroup):
    """PropertyGroup for storing project information.

    Attributes:
        name (str): Name of the project.
        role (str): User's role in the project.
        updated (str): Last update timestamp of the project.
        id (str): Unique identifier of the project.
    """
    # Blender properties use dynamic typing, so we need to ignore type checking
    name: bpy.props.StringProperty()  # type: ignore
    role: bpy.props.StringProperty(name="Role")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore

class SPECKLE_UL_projects_list(bpy.types.UIList):
    """Custom UIList for displaying Speckle projects.

    This UIList displays project information in either a DEFAULT/COMPACT layout
    or GRID layout, showing project name, role, and last updated timestamp.

    Attributes:
        layout_type (str): Current layout type ('DEFAULT', 'COMPACT', or 'GRID').
    """
    def draw_item(self, context: Context, layout: UILayout, data: PropertyGroup, item: PropertyGroup, icon: str, active_data: PropertyGroup, active_propname: str) -> None:
        """Draw a single project item in the UI list.

        Args:
            context (Context): Current Blender context.
            layout (UILayout): UI layout to draw in.
            data (PropertyGroup): Data containing the collection of items.
            item (PropertyGroup): Current item to draw.
            icon (str): Icon to display with the item.
            active_data (PropertyGroup): Data containing the active item.
            active_propname (str): Name of the active property.

        Returns:
            None
        """
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            split = row.split(factor=0.5) # This gives project name 1/2
            split.label(text=item.name)
            
            right_split = split.split(factor=0.5) # This gives project role and updated the other 1/2 of the row
            right_split.label(text=item.role)
            right_split.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name)

class SPECKLE_OT_project_selection_dialog(bpy.types.Operator):
    """Operator for managing project selection dialog.

    This operator handles the UI and logic for selecting Speckle projects,
    including account selection, project search, and project listing.

    Attributes:
        search_query (str): Search query for filtering projects.
        accounts (EnumProperty): Available accounts for selection.
        project_index (int): Index of currently selected project.
    """
    bl_idname = "speckle.project_selection_dialog"
    bl_label = "Select Project"

    def update_projects_list(self, context: Context) -> None:
        """Update the projects list based on selected account and search query.

        Args:
            context (Context): Current Blender context.

        Returns:
            None
        """
        wm = context.window_manager
        
        # Update the selected account ID in the window manager
        wm.selected_account_id = self.accounts
        
        # Clear existing projects
        wm.speckle_projects.clear()
        
        # Get projects for the selected account, using search if provided
        search = self.search_query if self.search_query.strip() else None
        projects: List[Tuple[str, str, str, str]] = get_projects_for_account(self.accounts, search=search)
        
        # Populate projects list in WindowManager
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
        update=update_projects_list
    )

    accounts: bpy.props.EnumProperty(  # type: ignore
        name="Account",
        description="Selected account to filter projects by",
        items=get_account_enum_items(),
        default=get_default_account_id(),
        update=update_projects_list
    )

    project_index: bpy.props.IntProperty(name="Project Index", default=0)  # type: ignore
    
    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.project_index < len(wm.speckle_projects):
            selected_project = wm.speckle_projects[self.project_index]
            bpy.ops.speckle.model_selection_dialog("INVOKE_DEFAULT", project_name=selected_project.name, project_id=selected_project.id)
        return {'FINISHED'}
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager
        
        # Ensure WindowManager has the projects collection
        if not hasattr(WindowManager, "speckle_projects"):
            # Register the collection property
            WindowManager.speckle_projects = bpy.props.CollectionProperty(type=speckle_project)
        
        # Clear existing projects
        wm.speckle_projects.clear()
        
        # Get the selected account
        selected_account_id = self.accounts

        if not hasattr(WindowManager, "selected_account_id"):
            # Register the collection property
            WindowManager.selected_account_id = bpy.props.StringProperty()
        wm.selected_account_id = selected_account_id
        
        # Fetch projects from server
        projects: List[Tuple[str, str, str, str]] = get_projects_for_account(selected_account_id)
        
        # Populate projects list in WindowManager
        for name, role, updated, id in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        
        # Account selection
        layout.prop(self, "accounts", text="")
        
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        # TODO: Add a button for adding a project by URL
        #row.operator("speckle.add_project_by_url", icon='URL', text="")
        
        # Projects UIList - now using WindowManager collection
        layout.template_list(
            "SPECKLE_UL_projects_list", "",
            context.window_manager, "speckle_projects",
            self, "project_index"
        )
        layout.separator()

class SPECKLE_OT_add_project_by_url(bpy.types.Operator):
    """Operator for adding a Speckle project by URL.

    This operator allows users to add a Speckle project by providing its URL.

    Attributes:
        url (str): URL of the project to add.
    """
    bl_idname = "speckle.add_project_by_url"
    bl_label = "Add Project by URL"
    bl_description = "Add a project from a URL"
    
    url: bpy.props.StringProperty(  # type: ignore
        name="Project URL",
        description="Enter the Speckle project URL",
        default=""
    )

    def execute(self, context: Context) -> set[str]:
        # TODO: Implement logic to add project using the URL
        self.report({'INFO'}, f"Adding project from URL: {self.url}")
        return {'FINISHED'}

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
    # Clean up WindowManager properties
    if hasattr(WindowManager, "speckle_projects"):
        del WindowManager.speckle_projects
    
    bpy.utils.unregister_class(SPECKLE_OT_add_project_by_url)
    bpy.utils.unregister_class(SPECKLE_OT_project_selection_dialog)
    bpy.utils.unregister_class(SPECKLE_UL_projects_list)
    bpy.utils.unregister_class(speckle_project)