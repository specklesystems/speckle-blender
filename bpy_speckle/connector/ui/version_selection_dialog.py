import bpy
from bpy.types import UILayout, Context, PropertyGroup, Event
from ..utils.version_manager import get_versions_for_model, get_latest_version


class SPECKLE_UL_versions_list(bpy.types.UIList):
    """
    UIList for displaying a list of Speckle versions
    """

    # TODO: Adjust column widths so message has the most space.
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
            split = row.split(factor=0.166)
            split.label(text=item.id)
            right_split = split.split(factor=0.7)
            right_split.label(text=item.message)
            right_split.label(text=item.updated)

        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.id)


class SPECKLE_OT_version_selection_dialog(bpy.types.Operator):
    bl_idname = "speckle.version_selection_dialog"
    bl_label = "Select Version"

    version_index: bpy.props.IntProperty(name="Model Index", default=0)  # type: ignore

    load_option: bpy.props.EnumProperty(  # type: ignore
        name="Load Option",
        description="Choose how to load the version",
        items=[
            ("LATEST", "Load latest version", "Load the latest version available"),
            (
                "SPECIFIC",
                "Load a specific version",
                "Load a specific version from the list",
            ),
        ],
        default="LATEST",
    )

    model_card_id: bpy.props.StringProperty(
        name="Model Card ID",
        description="This is used to indicate the function is called from a model card",
        default="",
    )  # type: ignore

    def update_versions_list(self, context: Context) -> None:
        wm = context.window_manager
        wm.speckle_versions.clear()

        versions = get_versions_for_model(
            account_id=wm.selected_account_id,
            project_id=wm.selected_project_id,
            model_id=wm.selected_model_id,
        )

        for id, message, updated in versions:
            version = wm.speckle_versions.add()
            version.id = id
            version.message = message
            version.updated = updated

        return None

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager

        version_id_to_store = ""

        if self.load_option == "LATEST":
            latest_version = get_latest_version(
                account_id=wm.selected_account_id,
                project_id=wm.selected_project_id,
                model_id=wm.selected_model_id,
            )
            if latest_version:
                version_id_to_store = latest_version[0]
            else:
                print(
                    f"Could not fetch latest version for model {wm.selected_model_id}"
                )
                return {"CANCELLED"}

        elif self.load_option == "SPECIFIC":
            if 0 <= self.version_index < len(wm.speckle_versions):
                selected_version = wm.speckle_versions[self.version_index]
                version_id_to_store = selected_version.id
            else:
                print(f"Invalid version index {self.version_index}")
                return {"CANCELLED"}
        wm.selected_version_id = version_id_to_store
        wm.selected_version_load_option = self.load_option

        if self.model_card_id != "":
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            if model_card is None:
                self.report({"ERROR"}, f"Model card '{self.model_card_id}' not found")
                return {"CANCELLED"}

            model_card.load_option = self.load_option
            model_card.version_id = version_id_to_store
            self.report(
                {"INFO"},
                f"Model card updated: Selected version: {version_id_to_store}, Option: {self.load_option}",
            )
            # call the load operator
            bpy.ops.speckle.model_card_load(model_card_id=self.model_card_id)
            context.area.tag_redraw()
            return {"FINISHED"}

        self.report(
            {"INFO"},
            f"Selected version: {version_id_to_store} (Option: {self.load_option})",
        )

        context.area.tag_redraw()

        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        if self.model_card_id != "":
            wm = context.window_manager
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            self.load_option = model_card.load_option
            wm.selected_account_id = model_card.account_id
            wm.selected_project_id = model_card.project_id
            wm.selected_model_id = model_card.model_id

        self.update_versions_list(context)

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        wm = context.window_manager
        project_name = wm.selected_project_name
        model_name = wm.selected_model_name
        if self.model_card_id != "":
            model_card = context.scene.speckle_state.get_model_card_by_id(
                self.model_card_id
            )
            project_name = model_card.project_name
            model_name = model_card.model_name

        layout.label(text=f"Project: {project_name}")
        layout.label(text=f"Model: {model_name}")

        layout.prop(
            self,
            "load_option",
            expand=True,
        )

        if self.load_option == "SPECIFIC":
            # Versions UIList
            layout.template_list(
                "SPECKLE_UL_versions_list",
                "",
                context.window_manager,
                "speckle_versions",
                self,
                "version_index",
            )

        layout.separator()
