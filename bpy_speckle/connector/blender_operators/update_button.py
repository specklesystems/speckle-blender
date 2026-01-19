import bpy
import webbrowser
from bpy.types import Context


class SPECKLE_OT_update_button(bpy.types.Operator):
    """Operator for opening the download URL for the latest Speckle Blender connector"""

    bl_idname = "speckle.update_button"
    bl_label = "Update"
    bl_description = "Download the latest version of the Speckle Blender connector"

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager

        if not wm.update_url:
            self.report({"ERROR"}, "No update URL available")
            return {"CANCELLED"}

        try:
            webbrowser.open(wm.update_url)
            self.report({"INFO"}, f"Opening download page for v{wm.latest_version}")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to open download page: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}
