import bpy
from bpy.types import Context


class SPECKLE_OT_version_check(bpy.types.Operator):
    """Operator for checking if a newer version of the Speckle Blender connector is available"""

    bl_idname = "speckle.version_check"
    bl_label = "Check for Updates"
    bl_description = (
        "Check if a newer version of the Speckle Blender connector is available"
    )

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager

        # Reset previous state
        wm.update_available = False
        wm.latest_version = ""
        wm.update_url = ""

        try:
            from specklepy.core.api.connector_versions import get_latest_version

            # Get current version from bl_info
            from ... import bl_info

            current_version = bl_info["version"]
            current_version_str = (
                f"{current_version[0]}.{current_version[1]}.{current_version[2]}"
            )

            # Get latest version info
            latest_version_info = get_latest_version("blender", False)
            latest_version_str = latest_version_info.number  # semantic version string

            # Compare versions - if they're different, show update
            if latest_version_str != current_version_str:
                wm.update_available = True
                wm.latest_version = latest_version_str
                wm.update_url = str(
                    latest_version_info.url
                )  # Convert HttpUrl to string
                self.report({"INFO"}, f"Update available: v{latest_version_str}")
            else:
                self.report({"INFO"}, "You have the latest version")

        except ImportError:
            error_msg = "specklepy not available for version checking"
            self.report({"ERROR"}, error_msg)
        except Exception as e:
            error_msg = f"Failed to check for updates: {str(e)}"
            self.report({"ERROR"}, error_msg)

        return {"FINISHED"}
