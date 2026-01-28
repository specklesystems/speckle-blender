import bpy
from bpy.types import Event, Context
from typing import Optional
from ..utils.authentication import (
    AuthenticationServer,
    DesktopServiceAuthenticator,
    SPECKLE_AUTH_PORT
)


# Global auth server/authenticator instance
_auth_server = None
_desktop_authenticator = None


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
        print(f"[Add Account] Starting authentication for server: {self.server_url}")
        cleanup_auth_server()
        
        # Try to start own auth server first - it will fail gracefully if port is in use
        global _auth_server
        _auth_server = AuthenticationServer(port=SPECKLE_AUTH_PORT)
        
        if _auth_server.start():
            return self._initiate_own_server_flow(context)
        
        # Server failed to start - assume Desktop Service is running
        _auth_server = None
        print(f"[Add Account] Port {SPECKLE_AUTH_PORT} in use, using Desktop Service")
        self.report({"INFO"}, "Authenticating via Speckle Desktop Service...")
        return self._initiate_desktop_service_flow(context)
    
    def _initiate_own_server_flow(self, context: Context) -> set[str]:
        """Start auth flow with our own server."""
        try:
            _auth_server.open_auth_url(self.server_url)
            self._start_modal_timer(context)
            return {"RUNNING_MODAL"}
        except Exception as e:
            print(f"[Add Account] Failed to open browser: {e}")
            self.report({"ERROR"}, f"Failed to open browser: {e}")
            cleanup_auth_server()
            return {"CANCELLED"}
    
    def _initiate_desktop_service_flow(self, context: Context) -> set[str]:
        """Start auth flow with Desktop Service."""
        global _desktop_authenticator
        _desktop_authenticator = DesktopServiceAuthenticator(self.server_url)
        
        if not _desktop_authenticator.start():
            error_msg = _desktop_authenticator.get_error_message()
            self.report({"ERROR"}, error_msg or "Failed to open browser. Please try again.")
            _desktop_authenticator = None
            return {"CANCELLED"}
        
        self._start_modal_timer(context)
        return {"RUNNING_MODAL"}
    
    def _start_modal_timer(self, context: Context):
        """Start modal timer for auth polling."""
        self._timeout_counter = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)

    def modal(self, context: Context, event: Event) -> set[str]:
        global _auth_server, _desktop_authenticator
        
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        
        # Check for timeout
        self._timeout_counter += 1
        if self._timeout_counter >= self._max_timeout:
            print("[Add Account] Authentication timed out after 5 minutes")
            self._cleanup(context)
            self.report({"WARNING"}, "Authentication timed out after 5 minutes. Please try again.")
            return {"CANCELLED"}
        
        # Check for no active authenticator
        if not _desktop_authenticator and not _auth_server:
            print("[Add Account] No active authenticator, cancelling")
            self._cleanup(context)
            return {"CANCELLED"}
        
        # Check Desktop Service authentication
        if _desktop_authenticator:
            _desktop_authenticator.check_for_new_account()
            if _desktop_authenticator.is_complete():
                return self._finish_auth(
                    context,
                    _desktop_authenticator.is_successful(),
                    _desktop_authenticator.get_error_message(),
                    "Desktop Service"
                )
        
        # Check own server authentication
        if _auth_server and _auth_server.is_complete():
            return self._finish_auth(
                context,
                _auth_server.is_successful(),
                _auth_server.get_error_message(),
                "Own server"
            )
        
        # Still waiting
        return {"RUNNING_MODAL"}
    
    def _finish_auth(
        self,
        context: Context,
        is_successful: bool,
        error_msg: Optional[str],
        auth_type: str
    ) -> set[str]:
        """Complete authentication and cleanup."""
        print(f"[Add Account] {auth_type} authentication complete. Success: {is_successful}")
        self._cleanup(context)
        return self._handle_auth_complete(context, is_successful, error_msg)
    
    def _handle_auth_complete(self, context: Context, is_successful: bool, error_msg: Optional[str]) -> set[str]:
        """Handle authentication completion and update UI state."""
        if is_successful:
            print("[Add Account] Account added successfully - refreshing UI")
            
            # Import account management functions
            from ..utils.account_manager import get_account_enum_items, _client_cache
            from ..ui.account_selection_dialog import update_workspaces_list, update_projects_list
            
            # Get the newly added account (most recent one)
            accounts = get_account_enum_items()
            if accounts and accounts[0][0] != "NO_ACCOUNTS":
                new_account_id = accounts[-1][0]  # Last account added
                
                # Set as selected account
                context.window_manager.selected_account_id = new_account_id
                
                # Clear client cache to force re-authentication
                _client_cache.clear()
                
                # Refresh UI state
                try:
                    update_workspaces_list(context)
                    update_projects_list(context)
                except Exception as e:
                    print(f"[Add Account] Error refreshing UI state: {e}")
                
                self.report({"INFO"}, "Account added successfully and is now active!")
            else:
                self.report({"INFO"}, "Account added successfully!")
            
            return {"FINISHED"}
        else:
            error_details = error_msg if error_msg else 'Unknown error'
            print(f"[Add Account] Authentication failed: {error_details}")
            self.report({"ERROR"}, f"Authentication failed: {error_details}")
            
            # Show persistent error popup with details
            # Store error in window manager for the popup operator
            context.window_manager["speckle_auth_error"] = error_details
            bpy.ops.speckle.show_auth_error('INVOKE_DEFAULT')
            
            return {"CANCELLED"}
    
    def _cleanup(self, context: Context):
        # Remove timer
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        
        # Shutdown auth server/authenticator
        cleanup_auth_server()


def cleanup_auth_server():
    """Shutdown auth server/authenticator on addon unload."""
    global _auth_server, _desktop_authenticator
    
    if _auth_server is not None:
        try:
            _auth_server.shutdown()
        except Exception as e:
            print(f"[Add Account] Failed to cleanup auth server: {e}")
            print(f"[Add Account] Port {SPECKLE_AUTH_PORT} may still be occupied")
        _auth_server = None
    
    if _desktop_authenticator is not None:
        _desktop_authenticator = None


class SPECKLE_OT_show_auth_error(bpy.types.Operator):
    """Show persistent error dialog for authentication failures."""
    
    bl_idname = "speckle.show_auth_error"
    bl_label = "Authentication Error"
    bl_options = {'INTERNAL'}
    
    def execute(self, context: Context) -> set[str]:
        # Clean up the temporary error message
        if "speckle_auth_error" in context.window_manager:
            del context.window_manager["speckle_auth_error"]
        return {"FINISHED"}
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_popup(self, width=450)
    
    def draw(self, context: Context):
        layout = self.layout
        
        # Error header
        box = layout.box()
        row = box.row()
        row.label(text="", icon='ERROR')
        row.label(text="Authentication Failed", icon='NONE')
        
        layout.separator()
        
        # Error details
        error_details = context.window_manager.get("speckle_auth_error", "Unknown error")
        col = layout.column(align=True)
        
        # Split long error messages with word wrap
        for line in error_details.split('\n'):
            if len(line) > 60:
                # Word wrap long lines
                words = line.split(' ')
                current_line = ""
                for word in words:
                    if len(current_line + word) < 60:
                        current_line += word + " "
                    else:
                        if current_line.strip():
                            col.label(text=current_line.strip())
                        current_line = word + " "
                if current_line.strip():
                    col.label(text=current_line.strip())
            else:
                col.label(text=line)
        
        layout.separator()
        
        # Close button
        layout.operator("speckle.dismiss_popup", text="Close", icon='X')


class SPECKLE_OT_dismiss_popup(bpy.types.Operator):
    """Dismiss popup dialog."""
    
    bl_idname = "speckle.dismiss_popup"
    bl_label = "Dismiss"
    bl_options = {'INTERNAL'}
    
    def execute(self, context: Context) -> set[str]:
        # Clean up any temporary data
        if "speckle_auth_error" in context.window_manager:
            del context.window_manager["speckle_auth_error"]
        return {"FINISHED"}

