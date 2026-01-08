import bpy
from bpy.types import UILayout, Context
from .icons import get_icon


class SPECKLE_PT_model_cards_panel(bpy.types.Panel):
    """
    Panel for displaying Speckle model cards.
    """

    bl_label = "Model Cards"
    bl_idname = "SPECKLE_PT_model_cards_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Speckle"
    bl_order = 1

    @classmethod
    def poll(cls, context: Context) -> bool:
        """Only show panel when model cards exist"""
        return bool(context.scene.speckle_state.model_cards)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout

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
