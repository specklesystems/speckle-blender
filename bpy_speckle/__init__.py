# MIT License

# Copyright (c) 2018-2021 Tom Svilans

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


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

import bpy

"""
Import PySpeckle and attempt install if not found
"""

try:
    import specklepy
except ModuleNotFoundError as error:
    print("Speckle not found.")
    # TODO: Implement automatic installation of speckle and dependencies
    # to the local Blender module folder

    # from .install_dependencies import install_dependencies
    # install_dependencies()

"""
Import SpeckleBlender classes
"""

from specklepy.api.client import SpeckleClient  # , SpeckleCache
from specklepy.logging import metrics

from bpy_speckle.ui import *
from bpy_speckle.properties import *
from bpy_speckle.operators import *
from bpy_speckle.callbacks import *
from bpy.app.handlers import persistent

"""
Add load handler to initialize Speckle when 
loading a Blender file
"""


@persistent
def load_handler(dummy):
    bpy.ops.speckle.users_load()


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
