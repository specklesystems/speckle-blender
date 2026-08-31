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
    "name": "Speckle Connector",
    "author": "Speckle",
    "version": (3, 999, 999),
    "blender": (4, 2, 0),
    "location": "3d viewport toolbar (N), under the Speckle tab.",
    "description": "Publish models to and load models from other AEC apps.",
    "wiki_url": "https://speckle.systems/connectors/blender",
    "category": "Scene",
}

# Blender deletes ``bl_info`` from extension modules once the add-on is enabled
# (``addon_utils.enable``: "Always remove as this is not expected to exist"),
# because ``blender_manifest.toml`` is the source of truth for extensions. The
# dict above is still what ``patch_version.py`` rewrites at release time, so
# alias it under a name Blender leaves alone and read provenance from that —
# a lazy ``from ... import bl_info`` inside a function fails at runtime.
ADDON_INFO = bl_info


# UI
from .connector.ui.main_panel import SPECKLE_PT_main_panel
from .connector.ui.update_panel import SPECKLE_PT_update_panel
from .connector.ui.model_cards_panel import SPECKLE_PT_model_cards_panel
from .connector.utils.account_manager import speckle_workspace
from .connector.ui.project_selection_dialog import (
    SPECKLE_OT_project_selection_dialog,
    SPECKLE_UL_projects_list,
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
from .connector.blender_operators.add_account_button import (
    SPECKLE_OT_show_auth_error,
    SPECKLE_OT_dismiss_popup,
)
from .connector.blender_operators.model_card_load_button import (
    SPECKLE_OT_load_model_card,
)
from .connector.blender_operators.model_card_publish_button import (
    SPECKLE_OT_publish_model_card,
)
from .connector.blender_operators.create_project import SPECKLE_OT_create_project
from .connector.blender_operators.create_model import SPECKLE_OT_create_model
from .connector.blender_operators.version_check import SPECKLE_OT_version_check
from .connector.blender_operators.update_button import SPECKLE_OT_update_button
from .connector.utils.account_manager import (
    speckle_account,
    get_startup_account_id,
    _client_cache,
)

# States
from .connector.states.speckle_state import (
    register as register_speckle_state,
    unregister as unregister_speckle_state,
)


from .connector.ui.workspace_selection_dialog import (
    SPECKLE_OT_workspace_selection_dialog,
    SPECKLE_UL_workspaces_list,
)

# Utils
from .connector.ui.account_selection_dialog import (
    SPECKLE_OT_account_selection_dialog,
    SPECKLE_UL_accounts_list,
)


def delayed_version_check():
    """Timer function to check for updates after addon startup"""
    try:
        bpy.ops.speckle.version_check()
    except Exception as e:
        print(f"[Speckle] Failed to check for updates: {e}")


def invoke_window_manager_properties():
    # Accounts
    WindowManager.speckle_accounts = bpy.props.CollectionProperty(type=speckle_account)
    WindowManager.selected_account_id = bpy.props.StringProperty()
    # Workspaces
    WindowManager.speckle_workspaces = bpy.props.CollectionProperty(
        type=speckle_workspace
    )
    WindowManager.selected_workspace = bpy.props.PointerProperty(type=speckle_workspace)
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
    WindowManager.apply_modifiers = bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply all modifiers to objects before conversion",
        default=True,
    )
    # Instance loading mode, shown in the panel's LOAD section
    WindowManager.instance_loading_mode = bpy.props.EnumProperty(  # type: ignore
        name="Instance Loading",
        description="Choose how to load instances",
        items=[
            (
                "INSTANCE_PROXIES",
                "Collection Instances",
                "Load objects as collection instances",
            ),
            (
                "LINKED_DUPLICATES",
                "Linked Duplicates",
                "Get objects as linked duplicates",
            ),
        ],
        default="INSTANCE_PROXIES",
    )
    # Update checking
    WindowManager.update_available = bpy.props.BoolProperty(default=False)
    WindowManager.latest_version = bpy.props.StringProperty(default="")
    WindowManager.update_url = bpy.props.StringProperty(default="")


# Classes to load
classes = (
    SPECKLE_PT_update_panel,
    SPECKLE_PT_main_panel,
    SPECKLE_PT_model_cards_panel,
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
    SPECKLE_OT_show_auth_error,
    SPECKLE_OT_dismiss_popup,
    SPECKLE_OT_load_model_card,
    SPECKLE_OT_publish_model_card,
    SPECKLE_OT_create_project,
    SPECKLE_OT_create_model,
    SPECKLE_OT_version_check,
    SPECKLE_OT_update_button,
    speckle_account,
    SPECKLE_UL_workspaces_list,
    SPECKLE_OT_workspace_selection_dialog,
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

    # Pre-warm client cache for the account the UI will pre-select
    try:
        startup_account_id = get_startup_account_id()
        if startup_account_id and startup_account_id != "NO_ACCOUNTS":
            print(f"[Speckle] Pre-warming client for account: {startup_account_id}")
            _client_cache.get_client(startup_account_id)
            print(
                f"[Speckle] Client pre-warming complete for account: {startup_account_id}"
            )
    except Exception as e:
        print(f"[Speckle] Failed to pre-warm client: {e}")

    # Use a timer to delay the version check
    bpy.app.timers.register(delayed_version_check, first_interval=2.0)


def unregister():
    # Clear any pending timers to prevent duplicate calls
    if bpy.app.timers.is_registered(delayed_version_check):
        bpy.app.timers.unregister(delayed_version_check)

    # Clean up authentication server
    from .connector.blender_operators.add_account_button import cleanup_auth_server

    cleanup_auth_server()

    icons.unload_icons()
    unregister_speckle_state()  # Unregister SpeckleState
    _client_cache.clear()
    for cls in classes:
        bpy.utils.unregister_class(cls)


# Run the register function when the script is executed
if __name__ == "__main__":
    register()
