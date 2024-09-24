import bpy
import os
import bpy.utils.previews

speckle_icons = None

def load_icons():
    global speckle_icons
    speckle_icons = bpy.utils.previews.new()
    icons_dir = os.path.dirname(__file__)
    speckle_icons.load("speckle_logo", os.path.join(icons_dir, "speckle-logo.png"), 'IMAGE')

def unload_icons():
    global speckle_icons
    bpy.utils.previews.remove(speckle_icons)

def get_icon(icon_name):
    global speckle_icons
    return speckle_icons[icon_name].icon_id