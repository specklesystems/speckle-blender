import bpy

class speckle_version(bpy.types.PropertyGroup):
    id: bpy.props.StringProperty(name="ID")
    message: bpy.props.StringProperty(name="Message")
    updated: bpy.props.StringProperty(name="Updated")
    source_app: bpy.props.StringProperty(name="Source")

class SPECKLE_UL_versions_list(bpy.types.UIList):
    #TODO: Adjust column widths so message has the most space.
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            split = row.split(factor=0.166)
            split.label(text=item.id)
            right_split = split.split(factor=0.7)
            right_split.label(text=item.message)
            right_split.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.id)

class SPECKLE_OT_version_selection_dialog(bpy.types.Operator):
    bl_idname = "speckle.version_selection_dialog"
    bl_label = "Select Version"

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default=""
    )

    project_name: bpy.props.StringProperty(
        name="Project Name",
        description="Name of the selected project",
        default=""
    )

    model_name: bpy.props.StringProperty(
        name="Model Name",
        description="Name of the selected model",
        default=""
    )

    versions = [
        ("648896", "Message 1", "12 day ago"),
        ("658465", "Message 2", "15 days ago"),
        ("154651", "Message 3", "20 days ago"),
    ]

    version_index: bpy.props.IntProperty(name="Model Index", default=0)


    def execute(self, context):
        model_card = context.scene.speckle_model_cards.add()
        model_card.project_name = self.project_name
        model_card.model_name = self.model_name
        model_card.is_publish = False
        # Store the selected version ID
        selected_version = context.scene.speckle_versions[self.version_index]
        model_card.version_id = selected_version.id
        return {'FINISHED'}

    def invoke(self, context, event):
        # Clear existing versions
        context.scene.speckle_versions.clear()
        # Populate with new versions
        for id, message, updated in self.versions:
            version = context.scene.speckle_versions.add()
            version.id = id
            version.message = message
            version.updated = updated
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Project: {self.project_name}")
        layout.label(text=f"Model: {self.model_name}")
        # TODO: Add more UI elements here.
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        # Versions UIList
        layout.template_list("SPECKLE_UL_versions_list", "", context.scene, "speckle_versions", self, "version_index")

        layout.separator()
