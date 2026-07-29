import bpy
import textwrap
from bpy.types import Event, Context
from typing import Optional
from ..utils.authentication import (
    AuthenticationServer,
    SPECKLE_AUTH_PORT,
)
from ..utils.dialog import (
    DIALOG_WIDTH,
    WIDE_DIALOG_WIDTH,
)


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
        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

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

        # Server failed to start - port is in use
        _auth_server = None
        print(f"[Add Account] Port {SPECKLE_AUTH_PORT} is already in use")
        self.report(
            {"ERROR"},
            f"Port {SPECKLE_AUTH_PORT} is already in use. Please close any application using it and try again.",
        )
        return {"CANCELLED"}

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

    def _start_modal_timer(self, context: Context):
        """Start modal timer for auth polling."""
        self._timeout_counter = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, window=context.window)
        wm.modal_handler_add(self)

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
                "Authentication timed out after 5 minutes. Please try again.",
            )
            return {"CANCELLED"}

        # Check for no active auth server
        if not _auth_server:
            print("[Add Account] No active auth server, cancelling")
            self._cleanup(context)
            return {"CANCELLED"}

        # Check auth server completion
        if _auth_server.is_complete():
            return self._finish_auth(
                context,
                _auth_server.is_successful(),
                _auth_server.get_error_message(),
                "Auth server",
            )

        # Still waiting
        return {"RUNNING_MODAL"}

    def _finish_auth(
        self,
        context: Context,
        is_successful: bool,
        error_msg: Optional[str],
        auth_type: str,
    ) -> set[str]:
        """Complete authentication and cleanup."""
        print(
            f"[Add Account] {auth_type} authentication complete. Success: {is_successful}"
        )
        self._cleanup(context)
        return self._handle_auth_complete(context, is_successful, error_msg)

    def _handle_auth_complete(
        self, context: Context, is_successful: bool, error_msg: Optional[str]
    ) -> set[str]:
        """Handle authentication completion and update UI state."""
        if is_successful:
            print("[Add Account] Account added successfully - refreshing UI")

            # Import account management functions
            from ..utils.account_manager import get_account_enum_items, _client_cache
            from ..utils.config_store import set_user_selected_account_id
            from ..ui.account_selection_dialog import (
                update_workspaces_list,
                update_projects_list,
            )

            # Get the newly added account (most recent one)
            accounts = get_account_enum_items()
            if accounts and accounts[0][0] != "NO_ACCOUNTS":
                new_account_id = accounts[-1][0]  # Last account added

                # Set as selected account
                context.window_manager.selected_account_id = new_account_id
                set_user_selected_account_id(new_account_id)

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
            error_details = error_msg if error_msg else "Unknown error"
            print(f"[Add Account] Authentication failed: {error_details}")
            self.report({"ERROR"}, f"Authentication failed: {error_details}")

            # Show persistent error popup with details
            # Store error in window manager for the popup operator
            context.window_manager["speckle_auth_error"] = error_details
            bpy.ops.speckle.show_auth_error("INVOKE_DEFAULT")

            return {"CANCELLED"}

    def _cleanup(self, context: Context):
        # Remove timer
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        # Shutdown auth server/authenticator
        cleanup_auth_server()


def cleanup_auth_server():
    """Shutdown auth server on addon unload."""
    global _auth_server

    if _auth_server is not None:
        try:
            _auth_server.shutdown()
        except Exception as e:
            print(f"[Add Account] Failed to cleanup auth server: {e}")
            print(f"[Add Account] Port {SPECKLE_AUTH_PORT} may still be occupied")
        _auth_server = None


class SPECKLE_OT_show_auth_error(bpy.types.Operator):
    """Show persistent error dialog for authentication failures."""

    bl_idname = "speckle.show_auth_error"
    bl_label = "Authentication Error"
    bl_options = {"INTERNAL"}

    def execute(self, context: Context) -> set[str]:
        # Clean up the temporary error message
        if "speckle_auth_error" in context.window_manager:
            del context.window_manager["speckle_auth_error"]
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_popup(self, width=WIDE_DIALOG_WIDTH)

    def draw(self, context: Context):
        layout = self.layout

        # Error header
        box = layout.box()
        row = box.row()
        row.label(text="", icon="ERROR")
        row.label(text="Authentication Failed", icon="NONE")

        layout.separator()

        # Error details
        error_details = context.window_manager.get(
            "speckle_auth_error", "Unknown error"
        )
        col = layout.column(align=True)

        # Wrap long error messages
        wrapper = textwrap.TextWrapper(width=60)
        for line in error_details.split("\n"):
            if line:
                for wrapped_line in wrapper.wrap(line):
                    col.label(text=wrapped_line)
            else:
                col.label(text="")

        layout.separator()

        # Close button
        layout.operator("speckle.dismiss_popup", text="Close", icon="X")


class SPECKLE_OT_dismiss_popup(bpy.types.Operator):
    """Dismiss popup dialog."""

    bl_idname = "speckle.dismiss_popup"
    bl_label = "Dismiss"
    bl_options = {"INTERNAL"}

    def execute(self, context: Context) -> set[str]:
        # Clean up any temporary data
        if "speckle_auth_error" in context.window_manager:
            del context.window_manager["speckle_auth_error"]
        return {"FINISHED"}
