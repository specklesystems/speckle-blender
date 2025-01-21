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

import bpy
from bpy.props import PointerProperty, CollectionProperty, StringProperty, IntProperty, IntVectorProperty
from .ui import icons
import json

# Ensure dependencies
from .installer import ensure_dependencies
ensure_dependencies(f"Blender {bpy.app.version[0]}.{bpy.app.version[1]}")


# UI
from .ui.main_panel import SPECKLE_PT_main_panel
from .ui.project_selection_dialog import SPECKLE_OT_project_selection_dialog, speckle_project, SPECKLE_UL_projects_list, SPECKLE_OT_add_project_by_url
from .ui.model_selection_dialog import SPECKLE_OT_model_selection_dialog, speckle_model, SPECKLE_UL_models_list
from .ui.version_selection_dialog import SPECKLE_OT_version_selection_dialog, speckle_version, SPECKLE_UL_versions_list
from .ui.selection_filter_dialog import SPECKLE_OT_selection_filter_dialog
from .ui.model_card import speckle_model_card
# Operators
from .operators.publish import SPECKLE_OT_publish
from .operators.load import SPECKLE_OT_load
from .operators.model_card_settings import SPECKLE_OT_model_card_settings, SPECKLE_OT_view_in_browser, SPECKLE_OT_view_model_versions

# States
from .states.speckle_state import register as register_speckle_state, unregister as unregister_speckle_state

def save_model_cards(scene):
    model_cards_data = [card.to_dict() for card in scene.speckle_state.model_cards]
    scene["speckle_model_cards_data"] = json.dumps(model_cards_data)

def load_model_cards(scene):
    if "speckle_model_cards_data" in scene:
        model_cards_data = json.loads(scene["speckle_model_cards_data"])
        scene.speckle_state.model_cards.clear()
        for card_data in model_cards_data:
            card = speckle_model_card.from_dict(card_data)
            scene.speckle_state.model_cards.add().update(card)


# Classes to load
classes = (
    SPECKLE_PT_main_panel, 
    SPECKLE_OT_publish, 
    SPECKLE_OT_load, 
    SPECKLE_OT_project_selection_dialog, speckle_project, SPECKLE_UL_projects_list, SPECKLE_OT_add_project_by_url,
    SPECKLE_OT_model_selection_dialog, speckle_model, SPECKLE_UL_models_list, 
    SPECKLE_OT_version_selection_dialog, speckle_version, SPECKLE_UL_versions_list, 
    SPECKLE_OT_selection_filter_dialog, 
    speckle_model_card, SPECKLE_OT_model_card_settings, SPECKLE_OT_view_in_browser, SPECKLE_OT_view_model_versions)

@bpy.app.handlers.persistent
def load_handler(dummy):
    load_model_cards(bpy.context.scene)

@bpy.app.handlers.persistent
def save_handler(dummy):
    save_model_cards(bpy.context.scene)

# Register and Unregister
def register():
    icons.load_icons()

    for cls in classes:
        bpy.utils.register_class(cls)
    register_speckle_state() # Register SpeckleState

    bpy.app.handlers.load_post.append(load_handler)
    bpy.app.handlers.save_post.append(save_handler)

def unregister():
    icons.unload_icons()
    unregister_speckle_state() # Unregister SpeckleState
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.app.handlers.load_post.remove(load_handler)
    bpy.app.handlers.save_post.remove(save_handler)

# Run the register function when the script is executed
if __name__ == "__main__":
    register()
