import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event, WindowManager
from ..utils.model_manager import get_models_for_project
from ..utils.version_manager import get_latest_version


class speckle_model(bpy.types.PropertyGroup):
    """
    PropertyGroup for storing model information
    """

    name: bpy.props.StringProperty()  # type: ignore
    id: bpy.props.StringProperty(name="ID")  # type: ignore
    updated: bpy.props.StringProperty(name="Updated")  # type: ignore


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
            split.label(text=item.name)

            right_split = split.split(factor=0.25)
            right_split.label(text=item.id)
            right_split.label(text=item.updated)

        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)


class SPECKLE_OT_model_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the model selection dialog
    """

    bl_idname = "speckle.model_selection_dialog"
    bl_label = "Select Model"

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

            latest_version = get_latest_version(
                account_id=wm.selected_account_id,
                project_id=wm.selected_project_id,
                model_id=wm.selected_model_id,
            )
            if latest_version:
                wm.selected_version_load_option = "LATEST"
                wm.selected_version_id = latest_version[0]

            print(f"Selected model: {selected_model.name} ({selected_model.id})")

            context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        self.update_models_list(context)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager
        layout.label(text=f"Project: {wm.selected_project_name}")

        row = layout.row(align=True)
        row.prop(self, "search_query", icon="VIEWZOOM", text="")

        layout.template_list(
            "SPECKLE_UL_models_list",
            "",
            context.window_manager,
            "speckle_models",
            self,
            "model_index",
        )

        layout.separator()


def register() -> None:
    bpy.utils.register_class(speckle_model)
    bpy.utils.register_class(SPECKLE_UL_models_list)
    bpy.utils.register_class(SPECKLE_OT_model_selection_dialog)


def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_model_selection_dialog)
    bpy.utils.unregister_class(SPECKLE_UL_models_list)
    bpy.utils.unregister_class(speckle_model)
