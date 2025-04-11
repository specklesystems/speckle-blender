"""Module for handling model selection dialog in the Speckle Blender addon.

This module provides the UI components and functionality for selecting models
from Speckle projects within Blender.
"""

import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event, WindowManager
from ..utils.model_manager import get_models_for_project

class speckle_model(bpy.types.PropertyGroup):
    """PropertyGroup for storing model information.

    This class stores information about a Speckle model including its name,
    ID, and last update time for display in the model selection dialog.

    Attributes:
        name: The display name of the model.
        id: The unique identifier of the model.
        updated: The last update timestamp of the model.
    """
    # Blender properties use dynamic typing, so we need to ignore type checking
    name: bpy.props.StringProperty()  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore

class SPECKLE_UL_models_list(bpy.types.UIList):
    """UIList for displaying a list of Speckle models.

    This class handles the visual representation of models in the model selection dialog.
    It displays model information in both default/compact and grid layouts.
    """

    def draw_item(self, context: Context, layout: UILayout, data: PropertyGroup, item: PropertyGroup, 
                 icon: str, active_data: PropertyGroup, active_propname: str) -> None:
        """Draws a single item in the model list.

        Args:
            context: The current Blender context.
            layout: The layout to draw the item in.
            data: The data containing the item.
            item: The item to draw.
            icon: The icon to use for the item.
            active_data: The data containing the active item.
            active_propname: The name of the active property.
        """
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

class SPECKLE_OT_model_selection_dialog(bpy.types.Operator):
    """Operator for displaying and handling the model selection dialog.

    This operator manages the UI and functionality for selecting Speckle models,
    including search capabilities and model list display.
    """
    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"

    def update_models_list(self, context: Context) -> None:
        """Updates the list of models based on the current project and search query.
        """
        wm = context.window_manager
        # Clear existing models
        wm.speckle_models.clear()
        
        # Get models for the selected project, using search if provided
        search = self.search_query if self.search_query.strip() else None
        models = get_models_for_project(wm.selected_account_id, wm.selected_project_id, search=search)
        
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

    model_index: bpy.props.IntProperty(name="Model Index", default=0)  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.model_index < len(wm.speckle_models):
            selected_model = wm.speckle_models[self.model_index]
            
            # Store selected model details in wm
            wm.selected_model_id = selected_model.id
            wm.selected_model_name = selected_model.name

            print(f"Selected model: {selected_model.name} ({selected_model.id})")
        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> set[str]:
        
        # Ensure WindowManager has the models collection
        if not hasattr(WindowManager, "speckle_models"):
            WindowManager.speckle_models = bpy.props.CollectionProperty(type=speckle_model)
        # Ensure selected_model_id and selected_model_name exists in Window Manager
        if not hasattr(WindowManager, "selected_model_id"):
            WindowManager.selected_model_id = bpy.props.StringProperty(name = "Selected Model ID")
        if not hasattr(WindowManager, "selected_model_name"):
            WindowManager.selected_model_name = bpy.props.StringProperty(name = "Selected Model Name")
            
        # Update models list
        self.update_models_list(context)

        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context: Context) -> None:
        layout : UILayout = self.layout
        wm = context.window_manager
        layout.label(text=f"Project: {wm.selected_project_name}")
        
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        
        # Models UIList
        layout.template_list("SPECKLE_UL_models_list", "", context.window_manager, "speckle_models", self, "model_index")

        layout.separator()

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