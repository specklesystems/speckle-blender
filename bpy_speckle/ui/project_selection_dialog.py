import bpy
from bpy.types import UILayout, Context, UIList, PropertyGroup, Operator, Event
from typing import List, Tuple
from ..utils.account_manager import get_account_enum_items, get_default_account_id

class speckle_project(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing projects.

    This PropertyGroup is used to store information about a project,
    such as its name, role, and update time.

    This is used in the project selection dialog.
    """
    name: bpy.props.StringProperty()
    role: bpy.props.StringProperty(name="Role")
    updated: bpy.props.StringProperty(name="Updated")
    id: bpy.props.StringProperty(name="ID")

class SPECKLE_UL_projects_list(bpy.types.UIList):
    """
    UIList for displaying a list of projects.

    This UIList is used to display a list of projects in a Blender dialog.
    This is used in the project selection dialog.
    """
    def draw_item(self, context: Context, layout: UILayout, data: PropertyGroup, item: PropertyGroup, icon: str, active_data: PropertyGroup, active_propname: str) -> None:
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
    """
    Operator for project selection dialog.
    """
    bl_idname = "speckle.project_selection_dialog"
    bl_label = "Select Project"

    def update_projects_list(self, context):
        wm = context.window_manager
        
        # Clear existing projects
        wm.speckle_projects.clear()
        
        # Get projects for the selected account, using search if provided
        search = self.search_query if self.search_query.strip() else None
        projects = get_projects_for_account(self.accounts, search=search)
        
        # Populate projects list in WindowManager
        for name, role, updated, id in projects:
            project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            
        return None

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default="",
        update=update_projects_list
    )

    accounts: bpy.props.EnumProperty(
        name="Account",
        description="Selected account to filter projects by",
        items=get_account_enum_items(),
        default=get_default_account_id(),
        update=update_projects_list
    )

    project_index: bpy.props.IntProperty(name="Project Index", default=0)
    
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
        projects = get_projects_for_account(selected_account_id)
        
        # Populate projects list in WindowManager
        for name, role, updated, id in projects:
            project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        
        # Account selection
        layout.prop(self, "accounts")
        
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
    """
    Operator for adding a project by URL.
    """
    bl_idname = "speckle.add_project_by_url"
    bl_label = "Add Project by URL"
    bl_description = "Add a project from a URL"
    
    url: bpy.props.StringProperty(
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

def register():
    bpy.utils.register_class(speckle_project)
    bpy.utils.register_class(SPECKLE_UL_projects_list)
    bpy.utils.register_class(SPECKLE_OT_project_selection_dialog)
    bpy.utils.register_class(SPECKLE_OT_add_project_by_url)

def unregister():
    # Clean up WindowManager properties
    if hasattr(WindowManager, "speckle_projects"):
        del WindowManager.speckle_projects
    
    bpy.utils.unregister_class(SPECKLE_OT_add_project_by_url)
    bpy.utils.unregister_class(SPECKLE_OT_project_selection_dialog)
    bpy.utils.unregister_class(SPECKLE_UL_projects_list)
    bpy.utils.unregister_class(speckle_project)