import bpy

from bpy_speckle.installer import ensure_dependencies

ensure_dependencies(f"Blender {bpy.app.version[0]}.{bpy.app.version[1]}")

from bpy.app.handlers import persistent
from specklepy.logging import metrics

from bpy_speckle.callbacks import *
from bpy_speckle.operators import *
from bpy_speckle.properties import *
from bpy_speckle.ui import *

bl_info = {
    "name": "SpeckleBlender 2.0",
    "author": "Speckle Systems",
    "version": (0, 2, 0),
    "blender": (2, 92, 0),
    "location": "3d viewport toolbar (N), under the Speckle tab.",
    "description": "The Speckle Connector using specklepy 2.0!",
    "warning": "This add-on is WIP and should be used with caution",
    "wiki_url": "https://github.com/specklesystems/speckle-blender",
    "category": "Scene",
}


"""
Import SpeckleBlender classes
"""

"""
Add load handler to initialize Speckle when 
loading a Blender file
"""


@persistent
def load_handler(dummy):
    pass
    # Calling users_load is an expensive operation, one that force users to wait a good 10s every time blender loads.
    # Until we can do this non-blocking, we will make the user hit the refresh button each time.
    # bpy.ops.speckle.users_load()

    # Instead, we shall just reset the user selection to an uninitiailised state
    bpy.ops.speckle.users_reset()


"""
Permanent handle on callbacks
"""

callbacks = {}

"""
Add Speckle classes for registering
"""

speckle_classes = []
speckle_classes.extend(operator_classes)
speckle_classes.extend(property_classes)
speckle_classes.extend(ui_classes)


def register():
    from bpy.utils import register_class

    for cls in speckle_classes:
        register_class(cls)

    metrics.set_host_app("blender", f"blender {bpy.app.version_string}")

    """
    Register all new properties
    """

    bpy.types.Scene.speckle = bpy.props.PointerProperty(type=SpeckleSceneSettings)
    bpy.types.Collection.speckle = bpy.props.PointerProperty(
        type=SpeckleCollectionSettings
    )
    bpy.types.Object.speckle = bpy.props.PointerProperty(type=SpeckleObjectSettings)

    """
    Add callbacks
    """

    # Callback for displaying the current user account on top of the 3d view
    # callbacks['view3d_status'] = ((
    #     bpy.types.SpaceView3D.draw_handler_remove, # Function pointer for removal
    #     bpy.types.SpaceView3D.draw_handler_add(draw_speckle_info, (None, None), 'WINDOW', 'POST_PIXEL'), # Add handler
    #     'WINDOW' # Callback space for removal
    #     ))

    bpy.app.handlers.load_post.append(load_handler)


def unregister():
    bpy.app.handlers.load_post.remove(load_handler)

    """
    Remove callbacks
    """

    for cb in callbacks.values():
        cb[0](cb[1], cb[2])

    from bpy.utils import unregister_class

    for cls in reversed(speckle_classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
