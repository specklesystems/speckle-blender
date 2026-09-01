from typing import Optional, Dict
import os
import bpy.utils.previews

speckle_icons: Optional[Dict[str, bpy.types.ImagePreview]] = None


def load_icons() -> None:
    global speckle_icons
    speckle_icons = bpy.utils.previews.new()
    icons_dir = os.path.dirname(__file__)
    speckle_logo_icon_path = os.path.join(icons_dir, "speckle-logo.png")
    if os.path.exists(speckle_logo_icon_path):
        speckle_icons.load("speckle_logo", speckle_logo_icon_path, "IMAGE")
    else:
        print(f"[Speckle] WARNING ‑ icon file not found: {speckle_logo_icon_path}")
    object_highlight_icon_path = os.path.join(icons_dir, "object-highlight.png")
    if os.path.exists(object_highlight_icon_path):
        speckle_icons.load("object_highlight", object_highlight_icon_path, "IMAGE")
    else:
        print(f"[Speckle] WARNING ‑ icon file not found: {object_highlight_icon_path}")


def unload_icons() -> None:
    global speckle_icons
    if speckle_icons is not None:
        bpy.utils.previews.remove(speckle_icons)


def get_icon(icon_name: str) -> int:
    global speckle_icons
    if speckle_icons is None:
        raise ValueError("Icons not loaded")
    return speckle_icons[icon_name].icon_id


# built-in Outliner icons per Blender object type; lives here (not in a dialog
# module) so pre-bootstrap imports of the UI package stay specklepy-free
ICON_BY_OBJECT_TYPE: Dict[str, str] = {
    "MESH": "OUTLINER_OB_MESH",
    "CURVE": "OUTLINER_OB_CURVE",
    "SURFACE": "OUTLINER_OB_SURFACE",
    "META": "OUTLINER_OB_META",
    "FONT": "OUTLINER_OB_FONT",
    "ARMATURE": "OUTLINER_OB_ARMATURE",
    "LATTICE": "OUTLINER_OB_LATTICE",
    "EMPTY": "OUTLINER_OB_EMPTY",
    "GPENCIL": "OUTLINER_OB_GREASEPENCIL",
    "CAMERA": "OUTLINER_OB_CAMERA",
    "LIGHT": "OUTLINER_OB_LIGHT",
    "SPEAKER": "OUTLINER_OB_SPEAKER",
    "LIGHT_PROBE": "OUTLINER_OB_LIGHTPROBE",
}


def get_icon_for_type(obj_type: str) -> str:
    return ICON_BY_OBJECT_TYPE.get(obj_type, "OBJECT_DATA")
