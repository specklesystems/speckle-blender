# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# ruff: noqa
import bpy
from bpy.types import WindowManager
from .connector.ui import icons

# Ensure dependencies
from .installer import ensure_dependencies

ensure_dependencies(f"Blender {bpy.app.version[0]}.{bpy.app.version[1]}")

bl_info = {
    "name": "Speckle Blender ",
    "author": "Speckle Systems",
    "version": (3, 999, 999),
    "blender": (4, 2, 0),
    "location": "3d viewport toolbar (N), under the Speckle tab.",
    "description": "The Speckle Connector using specklepy 3.x!",
    "warning": "This add-on is WIP and should be used with caution",
    "wiki_url": "https://github.com/specklesystems/speckle-blender",
    "category": "Scene",
}


# UI
from .connector.ui.main_panel import SPECKLE_PT_main_panel
from .connector.ui.project_selection_dialog import (
    SPECKLE_OT_project_selection_dialog,
    SPECKLE_UL_projects_list,
    speckle_workspace,
)
from .connector.ui.model_selection_dialog import (
    SPECKLE_OT_model_selection_dialog,
    SPECKLE_UL_models_list,
)
from .connector.ui.version_selection_dialog import (
    SPECKLE_OT_version_selection_dialog,
    SPECKLE_UL_versions_list,
)
from .connector.ui.selection_filter_dialog import SPECKLE_OT_selection_filter_dialog
from .connector.utils.property_groups import (
    speckle_project,
    speckle_model,
    speckle_version,
    speckle_object,
    speckle_collection,
    speckle_model_card,
)

# Operators
from .connector.blender_operators.publish_button import SPECKLE_OT_publish
from .connector.blender_operators.load_button import SPECKLE_OT_load
from .connector.blender_operators.model_card_settings import (
    SPECKLE_OT_model_card_settings,
    SPECKLE_OT_view_in_browser,
    SPECKLE_OT_view_model_versions,
    SPECKLE_OT_delete_model_card,
)
from .connector.blender_operators.select_objects import SPECKLE_OT_select_objects
from .connector.blender_operators.add_account_button import SPECKLE_OT_add_account
from .connector.blender_operators.model_card_load_button import (
    SPECKLE_OT_load_model_card,
)
from .connector.blender_operators.model_card_publish_button import (
    SPECKLE_OT_publish_model_card,
)
from .connector.blender_operators.add_project_by_url import (
    SPECKLE_OT_add_project_by_url,
)

from .connector.blender_operators.create_project import SPECKLE_OT_create_project
from .connector.blender_operators.create_model import SPECKLE_OT_create_model
from .connector.utils.account_manager import speckle_account

# States
from .connector.states.speckle_state import (
    register as register_speckle_state,
    unregister as unregister_speckle_state,
)

# Utils
from .connector.ui.account_selection_dialog import (
    SPECKLE_OT_account_selection_dialog,
    SPECKLE_UL_accounts_list,
)


def invoke_window_manager_properties():
    # Accounts
    WindowManager.speckle_accounts = bpy.props.CollectionProperty(type=speckle_account)
    WindowManager.selected_account_id = bpy.props.StringProperty()
    # Workspaces
    WindowManager.speckle_workspaces = bpy.props.CollectionProperty(
        type=speckle_workspace
    )
    WindowManager.selected_workspace_id = bpy.props.StringProperty()
    WindowManager.can_create_project_in_workspace = bpy.props.BoolProperty()
    # Projects
    WindowManager.speckle_projects = bpy.props.CollectionProperty(type=speckle_project)
    WindowManager.selected_project_id = bpy.props.StringProperty()
    WindowManager.selected_project_name = bpy.props.StringProperty()
    # Models
    WindowManager.speckle_models = bpy.props.CollectionProperty(type=speckle_model)
    WindowManager.selected_model_id = bpy.props.StringProperty()
    WindowManager.selected_model_name = bpy.props.StringProperty()
    # Versions
    WindowManager.speckle_versions = bpy.props.CollectionProperty(type=speckle_version)
    WindowManager.selected_version_id = bpy.props.StringProperty()
    WindowManager.selected_version_load_option = bpy.props.StringProperty()
    # Send / Publish buttons
    WindowManager.ui_mode = bpy.props.EnumProperty(  # type: ignore
        name="UI Mode",
        description="Publish or Load a model",
        items=[
            ("PUBLISH", "Publish", "Publish a model to Speckle", "EXPORT", 0),
            ("LOAD", "Load", "Load a model from Speckle", "IMPORT", 1),
        ],
        default="PUBLISH",
    )
    # Objects
    WindowManager.speckle_objects = bpy.props.CollectionProperty(type=speckle_object)


# Classes to load
classes = (
    SPECKLE_PT_main_panel,
    SPECKLE_OT_publish,
    SPECKLE_OT_load,
    SPECKLE_OT_project_selection_dialog,
    speckle_project,
    SPECKLE_UL_projects_list,
    speckle_workspace,
    SPECKLE_OT_model_selection_dialog,
    speckle_model,
    SPECKLE_UL_models_list,
    SPECKLE_OT_version_selection_dialog,
    speckle_version,
    SPECKLE_UL_versions_list,
    SPECKLE_OT_selection_filter_dialog,
    speckle_object,
    speckle_collection,
    speckle_model_card,
    SPECKLE_OT_model_card_settings,
    SPECKLE_OT_view_in_browser,
    SPECKLE_OT_view_model_versions,
    SPECKLE_OT_delete_model_card,
    SPECKLE_OT_select_objects,
    SPECKLE_OT_add_account,
    SPECKLE_OT_load_model_card,
    SPECKLE_OT_publish_model_card,
    SPECKLE_OT_add_project_by_url,
    SPECKLE_OT_create_project,
    SPECKLE_OT_create_model,
    speckle_account,
    SPECKLE_OT_account_selection_dialog,
    SPECKLE_UL_accounts_list,
)


# Register and Unregister
def register():
    icons.load_icons()

    for cls in classes:
        bpy.utils.register_class(cls)
    register_speckle_state()  # Register SpeckleState

    invoke_window_manager_properties()


def unregister():
    icons.unload_icons()
    unregister_speckle_state()  # Unregister SpeckleState
    for cls in classes:
        bpy.utils.unregister_class(cls)


# Run the register function when the script is executed
if __name__ == "__main__":
    register()
