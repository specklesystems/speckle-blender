import bpy
from bpy.types import UILayout, Context, UIList, PropertyGroup, Operator, Event
from ..utils.project_manager import get_projects_for_account

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

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default=""
    )

    project_index: bpy.props.IntProperty(name="Project Index", default=0)
    
    def execute(self, context: Context) -> set[str]:
        selected_project = context.scene.speckle_state.projects[self.project_index]
        bpy.ops.speckle.model_selection_dialog("INVOKE_DEFAULT", project_name=selected_project.name)
        return {'FINISHED'}
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        # Clear existing projects
        context.scene.speckle_state.projects.clear()
    
        # Get the selected account
        account_id = context.scene.speckle_state.account
        
        # Fetch projects from server
        projects = get_projects_for_account(account_id)
        
        # Populate projects list
        for name, role, updated in projects:
            project = context.scene.speckle_state.projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        # TODO: Add UI elements here
        layout : UILayout = self.layout
        # Account selection
        layout.prop(context.scene.speckle_state, "account", text="")

        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        row.operator("speckle.add_project_by_url", icon='URL', text="")
        
        # Projects UIList
        layout.template_list("SPECKLE_UL_projects_list", "", context.scene.speckle_state, "projects", self, "project_index")

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