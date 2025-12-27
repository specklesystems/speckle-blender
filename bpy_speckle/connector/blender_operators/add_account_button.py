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
        
        print(f"[Add Account] Starting authentication for server: {self.server_url}")
        
        # Clean up any previous auth server
        if _auth_server is not None:
            try:
                print("[Add Account] Cleaning up previous auth server")
                _auth_server.shutdown()
            except Exception as e:
                print(f"[Add Account] Error shutting down previous server: {e}")
            _auth_server = None
        
        # Create and start the auth server
        _auth_server = AuthenticationServer(port=29364)
        
        if not _auth_server.start():
            print("[Add Account] Failed to start authentication server")
            self.report(
                {"ERROR"},
                "Failed to start authentication server. Port 29364 may be in use. "
                "Please close Speckle Desktop Service if running."
            )
            _auth_server = None
            return {"CANCELLED"}
        
        # Open browser to initiate auth flow
        try:
            print("[Add Account] Opening browser for authentication")
            _auth_server.open_auth_url(self.server_url)
            self.report({"INFO"}, f"Opening browser to authenticate with {self.server_url}")
        except Exception as e:
            print(f"[Add Account] Failed to open browser: {e}")
            self.report({"ERROR"}, f"Failed to open browser: {e}")
            _auth_server.shutdown()
            _auth_server = None
            return {"CANCELLED"}
        
        # Start timer to poll for completion
        self._timeout_counter = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)
        
        print("[Add Account] Authentication flow initiated, waiting for completion...")
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event) -> set[str]:
        global _auth_server
        
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        
        # Check for timeout
        self._timeout_counter += 1
        if self._timeout_counter >= self._max_timeout:
            print("[Add Account] Authentication timed out after 5 minutes")
            self._cleanup(context)
            self.report(
                {"WARNING"},
                "Authentication timed out after 5 minutes. Please try again."
            )
            return {"CANCELLED"}
        
        # Check if auth is complete
        if _auth_server is None:
            print("[Add Account] Auth server is None, cancelling")
            self._cleanup(context)
            return {"CANCELLED"}
        
        if _auth_server.is_complete():
            # Check success status BEFORE cleanup
            is_successful = _auth_server.is_successful()
            error_msg = _auth_server.get_error_message() if not is_successful else None
            
            print(f"[Add Account] Authentication complete. Success: {is_successful}")
            
            # Now cleanup
            self._cleanup(context)
            
            if is_successful:
                print("[Add Account] Account added successfully - prompting user to restart")
                self.report({"INFO"}, "Account added successfully! Please restart Blender to use the new account.")
                
                # Show a persistent popup dialog prompting restart
                bpy.ops.speckle.show_restart_prompt('INVOKE_DEFAULT')
                
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


class SPECKLE_OT_show_restart_prompt(bpy.types.Operator):
    """Show persistent restart prompt after successful account addition."""
    
    bl_idname = "speckle.show_restart_prompt"
    bl_label = "Restart Required"
    bl_options = {'INTERNAL'}
    
    def execute(self, context: Context) -> set[str]:
        return {"FINISHED"}
    
    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_popup(self, width=400)
    
    def draw(self, context: Context):
        layout = self.layout
        
        # Success icon and message
        box = layout.box()
        row = box.row()
        row.label(text="", icon='CHECKMARK')
        row.label(text="Account Added Successfully!", icon='NONE')
        
        layout.separator()
        
        # Restart instruction
        col = layout.column(align=True)
        col.label(text="Your Speckle account has been added to the database.")
        col.label(text="Please restart Blender to use your new account.")
        
        layout.separator()
        
        # OK button
        layout.operator("speckle.dismiss_popup", text="OK", icon='CHECKMARK')


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

