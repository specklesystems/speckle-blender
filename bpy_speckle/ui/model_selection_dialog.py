import bpy

class speckle_model(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    source_app: bpy.props.StringProperty(name="Source")
    updated: bpy.props.StringProperty(name="Updated")

class SPECKLE_UL_models_list(bpy.types.UIList):
    #TODO: Adjust column widths so name has the most space.
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.name)
            row.label(text=item.source_app)
            row.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name)

class SPECKLE_OT_model_selection_dialog(bpy.types.Operator):
    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default=""
    )

    models = [
        ("94-workset name", "RVT", "1 day ago"),
        ("296/skp2skp3", "SKP", "16 days ago"),
        ("49/rhn2viewer", "RHN", "21 days ago"),
    ]

    model_index: bpy.props.IntProperty(name="Model Index", default=0)

    def execute(self, context):
        bpy.ops.speckle.version_selection_dialog("INVOKE_DEFAULT")
        return {'FINISHED'}

    def invoke(self, context, event):
        # Clear existing models
        context.scene.speckle_models.clear()
        # Populate with new projects
        for name, source_app, updated in self.models:
            model = context.scene.speckle_models.add()
            model.name = name
            model.source_app = source_app
            model.updated = updated
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        
        # Models UIList
        layout.template_list("SPECKLE_UL_models_list", "", context.scene, "speckle_models", self, "model_index")

        layout.separator()