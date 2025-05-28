import bpy
from bpy.types import Context, Event, UILayout, WindowManager
from ..utils.account_manager import (
    get_model_details_by_wrapper,
    get_project_from_url,
    can_load,
)


class SPECKLE_OT_add_project_by_url(bpy.types.Operator):
    """
    operator for adding a Speckle project by URL
    """

    bl_idname = "speckle.add_project_by_url"
    bl_label = "Add Project by URL"
    bl_description = "Add a project from a URL"

    url: bpy.props.StringProperty(  # type: ignore
        name="Project URL", description="Enter the Speckle project URL", default=""
    )

    def execute(self, context: Context) -> set[str]:
        self.report({"INFO"}, f"Adding project from URL: {self.url}")

        wm = context.window_manager

        # Get project from URL
        wrapper, client, project, error_message = get_project_from_url(self.url)

        if error_message:
            self.report({"ERROR"}, error_message)
            return {"CANCELLED"}

        # Get model details from the wrapper
        (
            account_id,
            project_id,
            project_name,
            model_id,
            model_name,
            version_id,
            load_option,
        ) = get_model_details_by_wrapper(wrapper)

        # Check permissions
        can_load_permission, permission_error = can_load(client, project)
        if not can_load_permission:
            self.report({"ERROR"}, permission_error)
            return {"CANCELLED"}

        # Update the window manager with the selected project/model/version
        wm.selected_account_id = account_id

        if project_id:
            wm.selected_project_id = project_id
            wm.selected_project_name = project_name
            if model_id:
                wm.selected_model_id = model_id
                wm.selected_model_name = model_name
                if version_id:
                    wm.selected_version_id = version_id
            wm.selected_version_id = version_id
            wm.selected_version_load_option = load_option

        context.window.screen = context.window.screen
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        # Ensure all required properties exist in WindowManager
        if not hasattr(WindowManager, "selected_account_id"):
            WindowManager.selected_account_id = bpy.props.StringProperty()

        if not hasattr(WindowManager, "selected_project_id"):
            WindowManager.selected_project_id = bpy.props.StringProperty(
                name="Selected Project ID"
            )
        if not hasattr(WindowManager, "selected_project_name"):
            WindowManager.selected_project_name = bpy.props.StringProperty(
                name="Selected Project Name"
            )

        if not hasattr(WindowManager, "selected_model_id"):
            WindowManager.selected_model_id = bpy.props.StringProperty(
                name="Selected Model ID"
            )
        if not hasattr(WindowManager, "selected_model_name"):
            WindowManager.selected_model_name = bpy.props.StringProperty(
                name="Selected Model Name"
            )

        if not hasattr(WindowManager, "selected_version_id"):
            WindowManager.selected_version_id = bpy.props.StringProperty(
                name="Selected Version ID"
            )

        if not hasattr(WindowManager, "selected_version_load_option"):
            WindowManager.selected_version_load_option = bpy.props.StringProperty(
                name="Selected Version Load Option"
            )

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "url", text="")
