import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event
from ..speckle_api import (
    can_create_model,
    get_latest_version,
    get_models_for_project,
)
from ..blender_operators.create_model import SPECKLE_OT_create_model
from ..utils.dialog import (
    DIALOG_WIDTH,
    invalidate_downstream_selection,
    redraw_ui,
)
from ..utils.misc import strip_non_renderable


class SPECKLE_UL_models_list(bpy.types.UIList):
    """
    UIList for displaying a list of Speckle models
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
            split = row.split(factor=0.5)
            split.label(text=strip_non_renderable(item.name))

            right_split = split.split(factor=0.25)
            right_split.label(text=item.id)
            right_split.label(text=item.updated)

        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=strip_non_renderable(item.name))


class SPECKLE_OT_model_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the model selection dialog
    """

    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"
    bl_description = "Select a model to load"

    def update_models_list(self, context: Context) -> None:
        wm = context.window_manager

        wm.speckle_models.clear()

        search = self.search_query if self.search_query.strip() else None
        models = get_models_for_project(
            wm.selected_account_id, wm.selected_project_id, search=search
        )

        for name, id, updated in models:
            model = wm.speckle_models.add()
            model.name = name
            model.updated = updated
            model.id = id

        return None

    search_query: bpy.props.StringProperty(  # type: ignore
        name="Search",
        description="Search a model",
        default="",
        update=update_models_list,
    )

    model_index: bpy.props.IntProperty(name="Model Index", default=0)  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        if 0 <= self.model_index < len(wm.speckle_models):
            selected_model = wm.speckle_models[self.model_index]

            wm.selected_model_id = selected_model.id
            wm.selected_model_name = selected_model.name
            invalidate_downstream_selection(wm, "MODEL")

            # Pre-select the latest version so LOAD is one click away. With no
            # version to point at, both props stay untouched — setting the
            # option without an id would label the panel button "Latest" while
            # Load stayed disabled — and a toast explains the disabled button.
            # Only in LOAD mode: a model with no versions is the normal case
            # when you are about to publish the first one.
            latest_version = get_latest_version(
                account_id=wm.selected_account_id,
                project_id=wm.selected_project_id,
                model_id=wm.selected_model_id,
            )
            if latest_version:
                wm.selected_version_load_option = "LATEST"
                wm.selected_version_id = latest_version[0]
            elif wm.ui_mode == "LOAD":
                # Deliberately vague: get_latest_version returns None both for
                # an empty model and for a failed request, so the console print
                # carries the diagnosis and the toast only says what the user
                # can act on.
                self.report(
                    {"INFO"},
                    f"No versions found for '{selected_model.name}' — nothing to load yet",
                )

            print(f"Selected model: {selected_model.name} ({selected_model.id})")

            redraw_ui(context)
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        self.update_models_list(context)

        wm = context.window_manager
        authorized, _ = can_create_model(wm.selected_account_id, wm.selected_project_id)
        self._can_create_model = authorized
        SPECKLE_OT_create_model._can_create = authorized

        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager
        layout.label(text=f"Project: {strip_non_renderable(wm.selected_project_name)}")

        row = layout.row(align=True)
        row.prop(self, "search_query", icon="VIEWZOOM", text="")  # search bar
        if wm.ui_mode != "LOAD":
            sub = row.row(align=True)
            sub.enabled = getattr(self, "_can_create_model", True)
            sub.operator("speckle.create_model", icon="ADD", text="")

        layout.template_list(
            "SPECKLE_UL_models_list",
            "",
            context.window_manager,
            "speckle_models",
            self,
            "model_index",
        )

        layout.separator()
