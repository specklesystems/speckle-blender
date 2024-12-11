"""
Addon properties
"""

import bpy


class SpeckleAddonPreferences(bpy.types.AddonPreferences):
    """
    Add-on preferences
    TODO: add any preferences that might be relevant here
    """

    bl_idname = __package__

    def draw(self, context):
        layout = self.layout
        layout.label(text="SpeckleBlender preferences")
