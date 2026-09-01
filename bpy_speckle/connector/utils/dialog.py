"""Shared plumbing for the connector's popup dialogs — sizing.

Blender fixes a dialog's width at invoke time — `draw()` has no say in it — so
every `invoke_props_dialog` / `invoke_popup` call site has to pass the width
itself. Keeping the number here means the connector's dialogs stay a
consistent size instead of drifting apart one call site at a time.

The unit is Blender UI units, not pixels: the value is multiplied by the user's
Resolution Scale before it reaches the screen. Blender's own default is 300.
"""

# Standard width for connector dialogs (account, project, model, version, ...).
DIALOG_WIDTH = 400

# Wider variant for dialogs carrying prose rather than a list — error messages
# and the like, where 400 units wraps into an unreadably tall column.
WIDE_DIALOG_WIDTH = 500


def redraw_ui(context) -> None:
    """Tag the Speckle panel for redraw, whatever context the caller runs in.

    `context.area` is the area a popup was spawned from and is normally set,
    but code running off the main loop (timers, handlers) sees whatever the
    mouse happens to be over, which may be None. Walking the window manager
    keeps the redraw working in both cases.
    """
    if context.area is not None:
        context.area.tag_redraw()
        return

    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def invalidate_downstream_selection(wm, changed: str) -> None:
    """Clear selections that the change to `changed` has made meaningless.

    `changed` is "PROJECT" or "MODEL".

    Model ids are scoped to a project and version ids to a model, so picking a
    new project would leave `selected_model_id` pointing at a model that does
    not exist under it. Policy: clear everything downstream of the change.
    The panel shows the selection as genuinely empty — Load / Publish disable
    until the user picks again — rather than keeping a stale name next to an
    enabled button. The project dialog's pasted-URL path is unaffected: it
    re-fills the model and version fields *after* this call.
    """
    if changed == "PROJECT":
        wm.selected_model_id = ""
        wm.selected_model_name = ""
    wm.selected_version_id = ""
    wm.selected_version_load_option = ""
