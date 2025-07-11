import bpy
from bpy.types import UILayout, Context
from .icons import get_icon


class SPECKLE_PT_main_panel(bpy.types.Panel):
    """
    main panel for the Speckle addon.
    """

    bl_label = "Speckle"

    bl_idname = "SPECKLE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Speckle"

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.label(text="Speckle Connector", icon_value=get_icon("speckle_logo"))

        # check to see if there are any speckle models in the file
        if not context.scene.speckle_state.model_cards:
            layout.label(text="Hello!")
            layout.label(text="There are no Speckle models in this file yet.")

        layout.separator()

        wm = context.window_manager
        project_selected = bool(getattr(wm, "selected_project_name", None))
        model_selected = bool(getattr(wm, "selected_model_name", None))
        version_selected = bool(getattr(wm, "selected_version_id", None))
        selection_made = bool(getattr(wm, "speckle_objects", None))

        # UI Mode Switch
        row = layout.row()
        row.prop(wm, "ui_mode", expand=True)

        # select Project button
        row = layout.row()
        project_name = getattr(wm, "selected_project_name", "")
        project_button_text = project_name if project_selected else "Select Project"
        project_button_icon = "CHECKMARK" if project_selected else "PLUS"
        row.operator(
            "speckle.project_selection_dialog",
            text=project_button_text,
            icon=project_button_icon,
        )

        # select Model button
        row = layout.row()
        model_name = getattr(wm, "selected_model_name", "")
        model_button_text = model_name if model_selected else "Select Model"
        model_button_icon = "CHECKMARK" if model_selected else "PLUS"
        row.enabled = project_selected
        row.operator(
            "speckle.model_selection_dialog",
            text=model_button_text,
            icon=model_button_icon,
        )
        if wm.ui_mode == "PUBLISH":
            # TODO: implement Publish flow
            # Selection filter
            row = layout.row()
            row.enabled = project_selected and model_selected
            selection_button_text = (
                f"{len(wm.speckle_objects)} Objects"
                if wm.speckle_objects
                else "Select Objects"
            )
            row.operator(
                "speckle.selection_filter_dialog",
                text=selection_button_text,
                icon="PLUS",
            ).model_card_id = ""

            # Publish button
            row = layout.row()
            row.enabled = project_selected and model_selected and selection_made
            row.operator("speckle.publish", text="Publish Model", icon="EXPORT")
            pass

        if wm.ui_mode == "LOAD":
            # select Version button
            row = layout.row()
            version_id = getattr(wm, "selected_version_id", "")
            load_option = getattr(wm, "selected_version_load_option", "")
            if load_option == "LATEST":
                version_button_text = "Latest"
            elif load_option == "SPECIFIC":
                version_button_text = version_id
            else:
                version_button_text = "Select Version"

            version_button_icon = "CHECKMARK" if version_selected else "PLUS"
            row.enabled = project_selected and model_selected
            row.operator(
                "speckle.version_selection_dialog",
                text=version_button_text,
                icon=version_button_icon,
            ).model_card_id = ""

            # load button
            row = layout.row()
            row.enabled = project_selected and model_selected and version_selected
            row.operator("speckle.load", text="Load Model", icon="IMPORT")

        layout.separator()

        # group model cards by project name
        project_groups = {}
        for model_card in context.scene.speckle_state.model_cards:
            project_name = (
                model_card.project_name if model_card.project_name else "No Project"
            )
            if project_name not in project_groups:
                project_groups[project_name] = []
            project_groups[project_name].append(model_card)

        for project_name, model_cards in project_groups.items():
            project_box = layout.box()
            project_row = project_box.row()
            project_row.label(text=f"Project: {project_name}", icon="TRIA_RIGHT")

            for model_card in model_cards:
                box: UILayout = project_box.box()
                row_1: UILayout = box.row()
                row_2: UILayout = box.row()

                if model_card.is_publish:
                    # Publish button in the model card
                    row_1.operator(
                        "speckle.model_card_publish", text="", icon="EXPORT"
                    ).model_card_id = model_card.get_model_card_id()
                    # Selection filter button in the model card
                    row_2.operator(
                        "speckle.selection_filter_dialog",
                        text=f"Selection: {len(model_card.objects)} objects",
                    ).model_card_id = model_card.get_model_card_id()
                elif not model_card.is_publish:
                    # Load button in the model card
                    row_1.operator(
                        "speckle.model_card_load", text="", icon="IMPORT"
                    ).model_card_id = model_card.get_model_card_id()
                    version_button_text = (
                        f"Latest: {model_card.version_id}"
                        if model_card.load_option == "LATEST"
                        else f"{model_card.version_id}"
                    )
                    row_2.operator(
                        "speckle.version_selection_dialog",
                        text=version_button_text,
                    ).model_card_id = model_card.get_model_card_id()
                    # TODO: Get last updated time

                else:
                    print({"ERROR"}, "Model card state unknown")
                    return

                row_1.label(text=f"{model_card.model_name}")

                # Select button in the model card
                select_op = row_1.operator(
                    "speckle.select_objects",
                    text="",
                    icon_value=get_icon("object_highlight"),
                )
                select_op.model_card_id = model_card.get_model_card_id()

                # Settings button in the model card
                row_1.operator(
                    "speckle.model_card_settings", text="", icon="COLLAPSEMENU"
                ).model_card_id = model_card.get_model_card_id()
