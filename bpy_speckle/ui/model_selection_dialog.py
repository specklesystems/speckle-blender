import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event, WindowManager
from .mouse_position_mixin import MousePositionMixin
from ..utils.model_manager import get_models_for_project

class speckle_model(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing models.

    This PropertyGroup is used to store information about a model,
    such as its name, ID and update time.

    These are then used in the model selection dialog.
    """
    # Blender properties use dynamic typing, so we need to ignore type checking
    name: bpy.props.StringProperty()  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore

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
            right_split.label(text=item.id)
            right_split.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name)

class SPECKLE_OT_model_selection_dialog(MousePositionMixin, bpy.types.Operator):
    """
    Operator for displaying a dialog for selecting a model.
    """
    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"

    def update_models_list(self, context: Context) -> None:
        wm = context.window_manager
        # Clear existing models
        wm.speckle_models.clear()
        
        # Get models for the selected project, using search if provided
        search = self.search_query if self.search_query.strip() else None
        models = get_models_for_project(wm.selected_account_id, self.project_id, search=search)
        
        # Populate models list
        for name, id, updated in models:
            model = wm.speckle_models.add()
            model.name = name
            model.updated = updated
            model.id = id
            
        return None

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search",
        description="Search a model",
        default="",
        update=update_models_list
    )

    project_name: bpy.props.StringProperty(  # type: ignore
        name="Project Name",
        description="The name of the project to select",
        default=""
    )

    project_id: bpy.props.StringProperty(  # type: ignore
        name="Project ID",
        description="The ID of the project to select",
        default=""
    )

    model_index: bpy.props.IntProperty(name="Model Index", default=0)  # type: ignore

    def execute(self, context: Context) -> set[str]:
        selected_model = context.window_manager.speckle_models[self.model_index]
        if context.scene.speckle_state.ui_mode == "PUBLISH":
            bpy.ops.speckle.selection_filter_dialog("INVOKE_DEFAULT", 
                project_name=self.project_name, 
                project_id=self.project_id,
                model_name=selected_model.name,
                model_id=selected_model.id)
        elif context.scene.speckle_state.ui_mode == "LOAD":
            bpy.ops.speckle.version_selection_dialog("INVOKE_DEFAULT", 
                project_name=self.project_name,
                project_id=self.project_id,
                model_name=selected_model.name,
                model_id=selected_model.id)
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> set[str]:
        
        # Ensure WindowManager has the projects collection
        if not hasattr(WindowManager, "speckle_models"):
            # Register the collection property
            WindowManager.speckle_models = bpy.props.CollectionProperty(type=speckle_model)

        # Update models list
        self.update_models_list(context)

        # Store the original mouse position
        self.init_mouse_position(context, event)

        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context: Context) -> None:
        layout : UILayout = self.layout
        layout.label(text=f"Project: {self.project_name}")
        
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        
        # Models UIList
        layout.template_list("SPECKLE_UL_models_list", "", context.window_manager, "speckle_models", self, "model_index")

        layout.separator()

        # Move cursor to original position
        self.restore_mouse_position(context)

def register() -> None:
    bpy.utils.register_class(speckle_model)
    bpy.utils.register_class(SPECKLE_UL_models_list)
    bpy.utils.register_class(SPECKLE_OT_model_selection_dialog)

def unregister() -> None:
    # Clean up WindowManager properties
    if hasattr(WindowManager, "speckle_models"):
        del WindowManager.speckle_models
    
    bpy.utils.unregister_class(SPECKLE_OT_model_selection_dialog)
    bpy.utils.unregister_class(SPECKLE_UL_models_list)
    bpy.utils.unregister_class(speckle_model)