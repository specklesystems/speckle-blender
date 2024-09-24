import bpy

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
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
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

    account: bpy.props.EnumProperty(
        name="Account",
        description="Select the account to filter projects by",
        items=[("account1", "Account 1", "Account 1"), ("account2", "Account 2", "Account 2")],
        default="account1"
    )

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default=""
    )

    projects = [
        ("RICK'S PORTAL", "contributor", "6 hours ago"),
        ("[BETA] Revit Tests", "owner", "6 hours ago"),
        ("Community Tickets", "owner", "a day ago"),
        ("Bilal's CNX Testing Space", "owner", "a day ago"),
        ("ArcGIS testing", "contributor", "3 days ago"),
    ] 

    project_index: bpy.props.IntProperty(name="Project Index", default=0)
    
    def execute(self, context):
        selected_project = context.scene.speckle_projects[self.project_index]
        bpy.ops.speckle.model_selection_dialog("INVOKE_DEFAULT", project_name=selected_project.name)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Clear existing projects
        context.scene.speckle_projects.clear()
    
    # Populate with new projects
        for name, role, updated in self.projects:
            project = context.scene.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
    
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        # TODO: Add UI elements here
        layout = self.layout
        # Account selection
        # TODO: Connect to Speckle API to get accounts
        layout.prop(self, "account", text="")

        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        
        # Projects UIList
        layout.template_list("SPECKLE_UL_projects_list", "", context.scene, "speckle_projects", self, "project_index")

        layout.separator()
