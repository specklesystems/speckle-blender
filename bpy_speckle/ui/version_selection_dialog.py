import bpy
from .mouse_position_mixin import MousePositionMixin
from ..utils.version_manager import get_versions_for_model

class speckle_version(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing versions.

    This PropertyGroup is used to store information about a version,
    such as its ID, message, and updated time.

    These are then used in the version selection dialog.
    """
    id: bpy.props.StringProperty(name="ID")
    message: bpy.props.StringProperty(name="Message")
    updated: bpy.props.StringProperty(name="Updated")
    source_app: bpy.props.StringProperty(name="Source")

class SPECKLE_UL_versions_list(bpy.types.UIList):
    """
    UIList for displaying a list of versions.

    This UIList is used to display a list of versions in the version selection dialog.
    """
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

class SPECKLE_OT_version_selection_dialog(MousePositionMixin, bpy.types.Operator):
    """
    Operator for selecting a version.
    """
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

    project_id: bpy.props.StringProperty(
        name="Project ID",
        description="ID of the selected project",
        default=""
    )

    model_id: bpy.props.StringProperty(
        name="Model ID",
        description="ID of the selected model",
        default=""
    )

    account_id: bpy.props.StringProperty(
        name="Account ID",
        description="ID of the current account",
        default=""
    )

    version_index: bpy.props.IntProperty(name="Model Index", default=0)

    def execute(self, context):
        model_card = context.scene.speckle_state.model_cards.add()
        model_card.project_name = self.project_name
        model_card.model_name = self.model_name
        model_card.is_publish = False
        # Store the selected version ID
        selected_version = context.window_manager.speckle_versions[self.version_index]
        model_card.version_id = selected_version.id
        return {'FINISHED'}

    def invoke(self, context, event):
        # Clear existing versions
        context.window_manager.speckle_versions.clear()
        # Fetch and populate versions
        versions = get_versions_for_model(
            account_id=self.account_id,
            project_id=self.project_id,
            model_id=self.model_id,
            search=self.search_query if self.search_query else None
        )
        for id, message, updated in versions:
            version = context.window_manager.speckle_versions.add()
            version.id = id
            version.message = message
            version.updated = updated
        
        # Initialize mouse position
        self.init_mouse_position(context, event)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Project: {self.project_name}")
        layout.label(text=f"Model: {self.model_name}")
        # TODO: Add more UI elements here.
        # TODO: Add more UI elements here.
        # TODO: Add more UI elements here.
        # Search field
        row = layout.row(align=True)
        row.prop(self, "search_query", icon='VIEWZOOM', text="")
        # Versions UIList
        row.template_list("SPECKLE_UL_versions_list", "", context.window_manager, "speckle_versions", self, "version_index")

        layout.separator()

        # Restore mouse position
        self.restore_mouse_position(context)
