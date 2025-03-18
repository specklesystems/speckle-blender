"""Module for handling version selection dialog in the Speckle Blender addon.

Provides the UI components and functionality for selecting versions.
"""

import bpy
from bpy.types import WindowManager, UILayout, Context, PropertyGroup, Event
from .mouse_position_mixin import MousePositionMixin
from ..utils.version_manager import get_versions_for_model
from ..utils.account_manager import get_server_url_by_account_id
from ..operators.load import SPECKLE_OT_load

class speckle_version(bpy.types.PropertyGroup):
    """PropertyGroup for storing version information.

    This class stores information about a Speckle version including its ID,
    version message, update time, and source application for display in the
    version selection dialog.

    Attributes:
        id: The unique identifier of the version.
        message: The version message associated with the version.
        updated: The last update timestamp of the version.
        source_app: The application that created this version.
    """
    # Blender properties use dynamic typing, so we need to ignore type checking
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    message: bpy.props.StringProperty(name="Message")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore
    source_app: bpy.props.StringProperty(name="Source")  # type: ignore

class SPECKLE_UL_versions_list(bpy.types.UIList):
    """UIList for displaying a list of Speckle versions.

    It displays version information in both default/compact and grid layouts.
    """
    #TODO: Adjust column widths so message has the most space.
    def draw_item(self, context: Context, layout: UILayout, data: PropertyGroup, item: PropertyGroup, icon: str, active_data: PropertyGroup, active_propname: str) -> None:
        """Draws a single item in the version list.

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
            split = row.split(factor=0.166)
            split.label(text=item.id)
            right_split = split.split(factor=0.7)
            right_split.label(text=item.message)
            right_split.label(text=item.updated)
        # This handles when the list is in a grid layout
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.id)

class SPECKLE_OT_version_selection_dialog(MousePositionMixin, bpy.types.Operator):
    """Operator for displaying and handling the version selection dialog.

    This operator manages the UI and functionality for selecting Speckle versions,
    including version list display and search capabilities.

    Attributes:
        search_query: The current search string for filtering versions.
        project_name: The name of the selected project.
        model_name: The name of the selected model.
        project_id: The ID of the selected project.
        model_id: The ID of the selected model.
        version_index: The index of the currently selected version.
    """
    bl_idname = "speckle.version_selection_dialog"
    bl_label = "Select Version"

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search",
        description="Search a project",
        default=""
    )

    project_name: bpy.props.StringProperty(  # type: ignore
        name="Project Name",
        description="Name of the selected project",
        default=""
    )

    model_name: bpy.props.StringProperty(  # type: ignore
        name="Model Name",
        description="Name of the selected model",
        default=""
    )

    project_id: bpy.props.StringProperty(  # type: ignore
        name="Project ID",
        description="ID of the selected project",
        default=""
    )

    model_id: bpy.props.StringProperty(  # type: ignore
        name="Model ID",
        description="ID of the selected model",
        default=""
    )

    version_index: bpy.props.IntProperty(name="Model Index", default=0)  # type: ignore

    def update_versions_list(self, context: Context) -> None:
        wm = context.window_manager
        # Clear existing versions
        wm.speckle_versions.clear()

        # Get versions for the selected model
        search = self.search_query if self.search_query.strip() else None
        versions = get_versions_for_model(
            account_id=wm.selected_account_id,
            project_id=self.project_id,
            model_id=self.model_id,
            search=search
        )

        # Populate versions list
        for id, message, updated in versions:
            version = wm.speckle_versions.add()
            version.id = id
            version.message = message
            version.updated = updated
        
        return None

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        model_card = context.scene.speckle_state.model_cards.add()
        model_card.server_url = get_server_url_by_account_id(account_id=wm.selected_account_id)
        model_card.project_name = self.project_name
        model_card.project_id = self.project_id
        model_card.model_id = self.model_id
        model_card.model_name = self.model_name
        model_card.is_publish = False
        # Store the selected version ID
        selected_version = context.window_manager.speckle_versions[self.version_index]
        model_card.version_id = selected_version.id

        # Call the load process class method
        SPECKLE_OT_load.load(context, model_card)

        return {'FINISHED'}

    def invoke(self, context: Context, event: Event) -> set[str]:
        # Ensure WindowManager has the versions collection
        if not hasattr(WindowManager, "speckle_versions"):
            # Register the collection property
            WindowManager.speckle_versions = bpy.props.CollectionProperty(type=speckle_version)

        # Update versions list
        self.update_versions_list(context)
        
        # Initialize mouse position
        self.init_mouse_position(context, event)

        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.label(text=f"Project: {self.project_name}")
        layout.label(text=f"Model: {self.model_name}")
        
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        # Versions UIList
        layout.template_list("SPECKLE_UL_versions_list", "", context.window_manager, "speckle_versions", self, "version_index")

        layout.separator()

        # Restore mouse position
        self.restore_mouse_position(context)
