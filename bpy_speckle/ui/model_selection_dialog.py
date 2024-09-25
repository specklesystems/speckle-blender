import bpy
from bpy.types import UILayout, Context, UIList, PropertyGroup, Operator, Event

class speckle_model(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing models.

    This PropertyGroup is used to store information about a model,
    such as its name, source application, and update time.

    These are then used in the model selection dialog.
    """
    name: bpy.props.StringProperty()
    source_app: bpy.props.StringProperty(name="Source")
    updated: bpy.props.StringProperty(name="Updated")

class SPECKLE_UL_models_list(bpy.types.UIList):
    """
    UIList for displaying a list of models.

    This UIList is used to display a list of models in model selection dialog.
    """
    #TODO: Adjust column widths so name has the most space.
    def draw_item(self, context: Context, layout: UILayout, data: PropertyGroup, item: PropertyGroup, icon: str, active_data: PropertyGroup, active_propname: str) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            split = row.split(factor=0.5)
            split.label(text=item.name)

            right_split = split.split(factor=0.25)
            right_split.label(text=item.source_app)
            right_split.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name)

class SPECKLE_OT_model_selection_dialog(bpy.types.Operator):
    """
    Operator for displaying a dialog for selecting a model.
    """
    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"

    search_query: bpy.props.StringProperty(
        name="Search",
        description="Search a project",
        default=""
    )

    project_name: bpy.props.StringProperty(
        name="Project Name",
        description="The name of the project to select",
        default=""
    )

    models: list[tuple[str, str, str]] = [
        ("94-workset name", "RVT", "1 day ago"),
        ("296/skp2skp3", "SKP", "16 days ago"),
        ("49/rhn2viewer", "RHN", "21 days ago"),
    ]

    model_index: bpy.props.IntProperty(name="Model Index", default=0)

    def execute(self, context: Context) -> set[str]:
        selected_model = context.scene.speckle_models[self.model_index]
        if context.scene.speckle_ui_mode == "PUBLISH":
            bpy.ops.speckle.selection_filter_dialog("INVOKE_DEFAULT", project_name=self.project_name, model_name=selected_model.name)
        elif context.scene.speckle_ui_mode == "LOAD":
            bpy.ops.speckle.version_selection_dialog("INVOKE_DEFAULT", project_name=self.project_name, model_name=selected_model.name)
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> set[str]:
        # Clear existing models
        context.scene.speckle_models.clear()
        # Populate with new projects
        for name, source_app, updated in self.models:
            model = context.scene.speckle_models.add()
            model.name = name
            model.source_app = source_app
            model.updated = updated
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context: Context) -> None:
        layout : UILayout = self.layout
        layout.label(text=f"Project: {self.project_name}")
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        
        # Models UIList
        layout.template_list("SPECKLE_UL_models_list", "", context.scene, "speckle_models", self, "model_index")

        layout.separator()
