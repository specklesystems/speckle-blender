import bpy
from bpy.types import UILayout, Context


class SPECKLE_PT_update_panel(bpy.types.Panel):
    """Panel for displaying connector update notifications"""

    bl_label = "Update Speckle"
    bl_idname = "SPECKLE_PT_update_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Speckle"
    bl_order = 0  # This ensures it appears above the main panel

    @classmethod
    def poll(cls, context: Context) -> bool:
        """Only show this panel when an update is available"""
        wm = context.window_manager
        return getattr(wm, "update_available", False)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager

        # Get current version from bl_info
        from ... import bl_info

        current_version = bl_info["version"]
        current_version_str = (
            f"{current_version[0]}.{current_version[1]}.{current_version[2]}"
        )

        # Update notification
        box = layout.box()
        box.alert = True  # Makes the box stand out with alert styling

        col = box.column()
        col.label(text="New version available!", icon="INFO")

        row = col.row()
        row.label(text=f"Current: v{current_version_str}")

        row = col.row()
        row.label(text=f"Latest: v{wm.latest_version}")

        # Update button
        row = col.row()
        row.operator("speckle.update_button", text="Download Update", icon="LINKED")
