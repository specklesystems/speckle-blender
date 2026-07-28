"""Shared plumbing for the connector's popup dialogs — sizing and chaining.

Blender fixes a dialog's width at invoke time — `draw()` has no say in it — so
every `invoke_props_dialog` / `invoke_popup` call site has to pass the width
itself. Keeping the number here means the connector's dialogs stay a
consistent size instead of drifting apart one call site at a time.

The unit is Blender UI units, not pixels: the value is multiplied by the user's
Resolution Scale before it reaches the screen. Blender's own default is 300.
"""

import bpy

# Standard width for connector dialogs (account, project, model, version, ...).
DIALOG_WIDTH = 400

# Wider variant for dialogs carrying prose rather than a list — error messages
# and the like, where 400 units wraps into an unreadably tall column.
WIDE_DIALOG_WIDTH = 500


def open_dialog_deferred(operator, **properties) -> None:
    """Open `operator` as a dialog once the current dialog has closed.

    Chaining one selection dialog into the next cannot be done directly:
    Blender tears down a popup's region *after* its `execute()` returns, so a
    dialog invoked from inside `execute()` is spawned into a context that is
    about to be freed, and it flickers shut instead of drawing. A one-shot
    timer puts the call back on the main loop, by which point the first dialog
    is properly gone.

    Pass every property the chained operator cares about explicitly. Blender
    remembers the last-used values for an operator type and reuses them on the
    next `bpy.ops` call, so an omitted property is not a default — it is
    whatever the previous invocation happened to leave behind.
    """

    def _open() -> None:
        operator("INVOKE_DEFAULT", **properties)
        return None  # returning None unregisters the timer: fire once

    bpy.app.timers.register(_open, first_interval=0.01)


def redraw_ui(context) -> None:
    """Tag the Speckle panel for redraw, from a dialog or a timer alike.

    `context.area` is the area a popup was spawned from — but a dialog opened
    by `open_dialog_deferred` runs off a timer, where `bpy.context.area` is
    whatever the mouse happens to be over, and may be None. Walking the window
    manager instead makes the redraw independent of how the dialog was opened.
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
    new project leaves `selected_model_id` pointing at a model that does not
    exist under it. The panel keeps showing the stale name, and its Load /
    Publish button stays enabled against a project+model pair that never
    existed together.

    TODO: decide the policy — see the note in the chat.
    """
    return None
