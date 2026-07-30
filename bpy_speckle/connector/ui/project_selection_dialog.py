import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event
from typing import List, Tuple
from ..utils.account_manager import (
    can_create_project_in_workspace,
    get_active_workspace,
    get_startup_account_id,
    get_account_from_id,
    get_server_url_by_account_id,
)
from ..utils.project_manager import get_projects_for_account
from ..utils.property_groups import speckle_project
from ..utils.url_resolver import (
    ParsedSpeckleUrl,
    UnsupportedUrlError,
    is_same_server,
    parse_speckle_url,
    resolve_speckle_url,
)
from ..utils.dialog import (
    DIALOG_WIDTH,
    invalidate_downstream_selection,
    redraw_ui,
)
from ..utils.misc import strip_non_renderable


class SPECKLE_UL_projects_list(bpy.types.UIList):
    """
    UIList for displaying a list of Speckle projects
    """

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: str,
        active_data: PropertyGroup,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            # enable/disable the row based on permission
            row.enabled = item.can_receive

            split = row.split(factor=0.5)
            split.label(text=strip_non_renderable(item.name))

            right_split = split.split(factor=0.5)
            right_split.label(text=item.role)
            right_split.label(text=item.updated)

        # handles when the list is in a grid layout
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.enabled = item.can_receive
            layout.label(text=strip_non_renderable(item.name))


def _select_project_from_url(props, context: Context, parsed: ParsedSpeckleUrl) -> None:
    """
    resolves a pasted URL against the selected account into a single-item
    project list, stashing the model/version parts for execute() to apply

    module-level rather than a method: property update callbacks may receive
    the operator's bare properties struct as `self`, which carries the
    property values but not the class's methods
    """
    wm = context.window_manager

    server_url = get_server_url_by_account_id(wm.selected_account_id)
    if not server_url or not is_same_server(server_url, parsed):
        props.url_error = (
            f"URL is for {parsed.host}, but the selected account is on {server_url}"
        )
        return

    resolved, error = resolve_speckle_url(
        wm.selected_account_id, parsed, resolve_version=wm.ui_mode == "LOAD"
    )
    if error:
        props.url_error = error
        return

    project: speckle_project = wm.speckle_projects.add()
    project.name = resolved.project_name
    project.role = resolved.role
    project.updated = resolved.updated
    project.id = resolved.project_id
    project.can_receive = resolved.can_receive
    props.project_index = 0

    props.url_model_id = resolved.model_id
    props.url_model_name = resolved.model_name
    props.url_version_id = resolved.version_id
    props.url_load_option = resolved.load_option


class SPECKLE_OT_project_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the project selection dialog
    """

    bl_idname = "speckle.project_selection_dialog"
    bl_label = "Select Project"
    bl_description = "Select a project to load models from"

    def update_projects_list(self, context: Context) -> None:
        """
        updates the list of projects based on the selected account and search query;
        a pasted project/model/version URL resolves to a single-item list instead
        """
        wm = context.window_manager

        self.url_error = ""
        self.url_model_id = ""
        self.url_model_name = ""
        self.url_version_id = ""
        self.url_load_option = ""

        wm.can_create_project_in_workspace = can_create_project_in_workspace(
            wm.selected_account_id, wm.selected_workspace.id
        )
        wm.speckle_projects.clear()

        try:
            parsed = parse_speckle_url(self.search_query)
        except UnsupportedUrlError as error:
            self.url_error = str(error)
            return None

        if parsed:
            _select_project_from_url(self, context, parsed)
            return None

        # get projects for the selected account, using search if provided
        search = self.search_query if self.search_query.strip() else None
        projects: List[Tuple[str, str, str, str, bool]] = get_projects_for_account(
            wm.selected_account_id, search=search, workspace_id=wm.selected_workspace.id
        )

        for name, role, updated, id, can_receive in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            project.can_receive = can_receive
        print("Updated Projects List!")
        return None

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search or Paste a URL",
        description="Search a project or paste a URL to add a project",
        default="",
        update=update_projects_list,
    )

    project_index: bpy.props.IntProperty(name="Project Index", default=0)  # type: ignore

    # what a pasted URL resolved to, applied on confirm; SKIP_SAVE because
    # operator properties are otherwise sticky across dialog invocations
    url_error: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})  # type: ignore
    url_model_id: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})  # type: ignore
    url_model_name: bpy.props.StringProperty(
        default="", options={"HIDDEN", "SKIP_SAVE"}
    )  # type: ignore
    url_version_id: bpy.props.StringProperty(
        default="", options={"HIDDEN", "SKIP_SAVE"}
    )  # type: ignore
    url_load_option: bpy.props.StringProperty(
        default="", options={"HIDDEN", "SKIP_SAVE"}
    )  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager

        if self.url_error:
            self.report({"ERROR"}, self.url_error)
            return {"CANCELLED"}

        if 0 <= self.project_index < len(wm.speckle_projects):
            selected_project = wm.speckle_projects[self.project_index]

            # verify the user has permission to receive from this project
            if not selected_project.can_receive:
                self.report(
                    {"ERROR"},
                    "Your role on this project doesn't give you permission to load.",
                )
                return {"CANCELLED"}

            wm.selected_project_id = selected_project.id
            wm.selected_project_name = selected_project.name
            invalidate_downstream_selection(wm, "PROJECT")

            # a pasted model/version URL selects the whole chain in one confirm
            if self.url_model_id:
                wm.selected_model_id = self.url_model_id
                wm.selected_model_name = self.url_model_name
                invalidate_downstream_selection(wm, "MODEL")
                if self.url_version_id:
                    wm.selected_version_load_option = self.url_load_option
                    wm.selected_version_id = self.url_version_id

            print(f"Selected project: {selected_project.name} ({selected_project.id})")

            redraw_ui(context)
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager

        # Clear existing projects
        wm.speckle_projects.clear()

        if wm.selected_account_id == "":
            wm.selected_account_id = get_startup_account_id()

        active_workspace = get_active_workspace(wm.selected_account_id)
        if active_workspace:
            wm.selected_workspace.id = active_workspace["id"]
            wm.selected_workspace.name = active_workspace["name"]
        else:
            from .account_selection_dialog import update_workspaces_list

            update_workspaces_list(context)
            workspaces = list(wm.speckle_workspaces)
            if workspaces:
                wm.selected_workspace.id = workspaces[0].id
                wm.selected_workspace.name = workspaces[0].name

        # Fetch projects from server
        projects: List[Tuple[str, str, str, str, bool]] = get_projects_for_account(
            wm.selected_account_id, wm.selected_workspace.id
        )

        for name, role, updated, id, can_receive in projects:
            project: speckle_project = wm.speckle_projects.add()
            project.name = name
            project.role = role
            project.updated = updated
            project.id = id
            project.can_receive = can_receive

        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager

        # Account selection
        row = layout.row()

        if wm.selected_account_id == "NO_ACCOUNTS":
            row.operator("speckle.add_account", icon="WORLD", text="Sign In")

        # if no accounts then don't show workspaces or projects list
        if wm.selected_account_id != "NO_ACCOUNTS":
            account = get_account_from_id(wm.selected_account_id)

            row.operator(
                "speckle.account_selection_dialog",
                icon="USER",
                text=f"{strip_non_renderable(account.userInfo.name)} - {account.userInfo.email} - {account.serverInfo.url}",
            )
            # Workspace selection
            row = layout.row()
            row.operator(
                "speckle.workspace_selection_dialog",
                icon="WORKSPACE",
                text=strip_non_renderable(wm.selected_workspace.name),
            )

            # Search field
            row = layout.row(align=True)
            row.prop(
                self,
                "search_query",
                icon="VIEWZOOM",
                text="",
                placeholder="Search or paste a URL",
            )
            # create project button
            # hide if in load mode
            if wm.ui_mode != "LOAD":
                split = row.split()
                split.operator("speckle.create_project", icon="ADD", text="")
                split.enabled = wm.can_create_project_in_workspace

            if self.url_error:
                row = layout.row()
                row.label(text=self.url_error, icon="ERROR")
            else:
                if self.url_model_id:
                    url_model_name = strip_non_renderable(self.url_model_name)
                    if self.url_load_option == "SPECIFIC":
                        hint = (
                            f"Also selects model '{url_model_name}'"
                            f" @ {self.url_version_id}"
                        )
                    elif self.url_load_option == "LATEST":
                        hint = f"Also selects model '{url_model_name}' (latest version)"
                    else:
                        hint = f"Also selects model '{url_model_name}'"
                    row = layout.row()
                    row.label(text=hint, icon="LINKED")

                layout.template_list(
                    "SPECKLE_UL_projects_list",
                    "",
                    context.window_manager,
                    "speckle_projects",
                    self,
                    "project_index",
                )
            layout.separator()
