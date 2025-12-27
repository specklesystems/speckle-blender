import bpy
from bpy.types import Event, Context
from ..utils.authentication import AuthenticationServer


# Global auth server instance
_auth_server = None


class SPECKLE_OT_add_account(bpy.types.Operator):
    """Operator for adding a new Speckle account."""

    bl_idname = "speckle.add_account"
    bl_label = "Add New Account"
    bl_description = "Add a new account"

    server_url: bpy.props.StringProperty(  # type: ignore
        name="Server URL",
        description="Speckle server URL to connect to",
        default="https://app.speckle.systems",
    )
    
    _timer = None
    _timeout_counter = 0
    _max_timeout = 300  # 5 minutes in seconds (300 checks at ~1 sec intervals)

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        layout = self.layout
        # Server URL textbox
        layout.prop(self, "server_url", text="Server URL")

    def execute(self, context: Context) -> set[str]:
        global _auth_server
        
        # Clean up any previous auth server
        if _auth_server is not None:
            try:
                _auth_server.shutdown()
            except Exception as e:
                print(f"[Add Account] Error shutting down previous server: {e}")
            _auth_server = None
        
        # Create and start the auth server
        _auth_server = AuthenticationServer(port=29364)
        
        if not _auth_server.start():
            self.report(
                {"ERROR"},
                "Failed to start authentication server. Port 29364 may be in use. "
                "Please close Speckle Desktop Service if running."
            )
            _auth_server = None
            return {"CANCELLED"}
        
        # Open browser to initiate auth flow
        try:
            _auth_server.open_auth_url(self.server_url)
            self.report({"INFO"}, f"Opening browser to authenticate with {self.server_url}")
        except Exception as e:
            self.report({"ERROR"}, f"Failed to open browser: {e}")
            _auth_server.shutdown()
            _auth_server = None
            return {"CANCELLED"}
        
        # Start timer to poll for completion
        self._timeout_counter = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)
        
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event) -> set[str]:
        global _auth_server
        
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        
        # Check for timeout
        self._timeout_counter += 1
        if self._timeout_counter >= self._max_timeout:
            self._cleanup(context)
            self.report(
                {"WARNING"},
                "Authentication timed out after 5 minutes. Please try again."
            )
            return {"CANCELLED"}
        
        # Check if auth is complete
        if _auth_server is None:
            self._cleanup(context)
            return {"CANCELLED"}
        
        if _auth_server.is_complete():
            # Check success status BEFORE cleanup
            is_successful = _auth_server.is_successful()
            error_msg = _auth_server.get_error_message() if not is_successful else None
            
            # Now cleanup
            self._cleanup(context)
            
            if is_successful:
                self.report({"INFO"}, "Account added successfully!")
                
                # Force UI refresh to show new account
                context.window.screen = context.window.screen
                context.area.tag_redraw()
                
                return {"FINISHED"}
            else:
                self.report(
                    {"ERROR"},
                    f"Authentication failed: {error_msg if error_msg else 'Unknown error'}"
                )
                return {"CANCELLED"}
        
        # Still waiting for auth to complete
        return {"RUNNING_MODAL"}
    
    def _cleanup(self, context: Context):
        """Clean up timer and auth server."""
        global _auth_server
        
        # Remove timer
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        
        # Shutdown auth server
        if _auth_server is not None:
            try:
                _auth_server.shutdown()
            except Exception as e:
                print(f"[Add Account] Error during cleanup: {e}")
            _auth_server = None


def cleanup_auth_server():
    """
    Global cleanup function to shutdown auth server.
    Should be called when Blender exits or the addon is unloaded.
    """
    global _auth_server
    if _auth_server is not None:
        try:
            _auth_server.shutdown()
        except Exception:
            pass
        _auth_server = None
