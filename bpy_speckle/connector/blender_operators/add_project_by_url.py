import bpy
from bpy.types import Context, Event, UILayout, WindowManager
from specklepy.api.wrapper import StreamWrapper
from typing import Tuple


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
        try:
            wrapper = StreamWrapper(self.url)
        except Exception as e:
            self.report({"ERROR"}, f"Failed to process URL: {str(e)}")
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

        client = wrapper.get_client()
        project = client.project.get(project_id)

        if not project:
            self.report({"ERROR"}, "Could not access project")
            return {"CANCELLED"}

        # check if user is workspace admin
        is_workspace_admin = False
        if hasattr(project, "workspace_id") and project.workspace_id:
            try:
                workspace = client.workspace.get(project.workspace_id)
                if workspace and workspace.role:
                    is_workspace_admin = "workspace:admin" in workspace.role
            except Exception as e:
                print(f"Cannot access to workspace: {e}")

        # check permisson
        role = getattr(project, "role", "")
        can_receive = False

        if role:
            if is_workspace_admin:
                can_receive = "stream:reviewer" not in role
            else:
                can_receive = any(
                    r in role for r in ["stream:owner", "stream:contributor"]
                )
        else:
            can_receive = is_workspace_admin

        if not can_receive:
            self.report(
                {"ERROR"},
                "Your role on this project doesn't give you permission to load.",
            )
            return {"CANCELLED"}

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


def register() -> None:
    bpy.utils.register_class(SPECKLE_OT_add_project_by_url)


def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_add_project_by_url)


def get_model_details_by_wrapper(
    wrapper: StreamWrapper,
) -> Tuple[str, str, str, str, str, str, str]:
    client = wrapper.get_client()
    client.authenticate_with_account(wrapper.get_account())
    (
        account_id,
        project_id,
        project_name,
        model_id,
        model_name,
        version_id,
        load_option,
    ) = "", "", "", "", "", "", ""
    account_id = wrapper.get_account().id
    if wrapper.stream_id:
        project_id = wrapper.stream_id
        project_name = client.project.get(project_id).name
    if wrapper.model_id:
        model_id = wrapper.model_id
        model = client.model.get(model_id, project_id)
        model_name = model.name
        load_option = "LATEST" if not wrapper.commit_id else "SPECIFIC"
        version_id = (
            wrapper.commit_id
            if wrapper.commit_id
            else client.version.get_versions(
                wrapper.model_id, wrapper.stream_id, limit=1
            )
            .items[0]
            .id
        )
    return (
        account_id,
        project_id,
        project_name,
        model_id,
        model_name,
        version_id,
        load_option,
    )
