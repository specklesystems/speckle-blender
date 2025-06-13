from typing import Optional, Dict
import os
import bpy.utils.previews

speckle_icons: Optional[Dict[str, bpy.types.ImagePreview]] = None


def load_icons() -> None:
    global speckle_icons
    speckle_icons = bpy.utils.previews.new()
    icons_dir = os.path.dirname(__file__)
    speckle_icons.load(
        "speckle_logo", os.path.join(icons_dir, "speckle-logo.png"), "IMAGE"
    )
    speckle_icons.load(
        "object_highlight",
        os.path.join(icons_dir, "object-highlight.png"),
        "IMAGE",
    )


def unload_icons() -> None:
    global speckle_icons
    if speckle_icons is not None:
        bpy.utils.previews.remove(speckle_icons)


def get_icon(icon_name: str) -> int:
    global speckle_icons
    if speckle_icons is None:
        raise ValueError("Icons not loaded")
    return speckle_icons[icon_name].icon_id
