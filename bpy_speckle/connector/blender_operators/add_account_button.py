import bpy
import webbrowser
from typing import Set
from bpy.types import Event, Context, UILayout

class SPECKLE_OT_add_account(bpy.types.Operator):
    """Operator for adding a new Speckle account.
    """
    bl_idname = "speckle.add_account"
    bl_label = "Add New Account"
    bl_description = "Add a new account"
    
    server_url: bpy.props.StringProperty(  # type: ignore
        name="Server URL",
        description="Speckle server URL to connect to",
        default="https://app.speckle.systems"
    )
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context: Context):
        layout = self.layout
        # Server URL textbox
        layout.prop(self, "server_url", text="Server URL")
    
    def execute(self, context: Context) -> set[str]:
        # Logic to handle sign in
        api_url = "http://localhost:29364"
        url = f"{api_url}/auth/add-account?serverUrl={self.server_url}"
        webbrowser.open(url)
        self.report({'INFO'}, f"Adding account from {self.server_url}: {url}")
        
        # Force a redraw of all areas to refresh the UI
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
            
        return {'FINISHED'}