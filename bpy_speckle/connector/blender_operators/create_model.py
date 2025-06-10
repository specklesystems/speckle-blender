import bpy
from bpy.types import Context, Event, UILayout
from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts
from specklepy.core.api.credentials import Account
from specklepy.core.api.inputs import CreateModelInput
from typing import List, Tuple, Optional


class SPECKLE_OT_create_model(bpy.types.Operator):
    bl_idname = "speckle.create_model"
    bl_label = "Create Model"
    bl_description = "Create a new Speckle model"

    model_name: bpy.props.StringProperty(name="Model Name")  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        model_id, model_name = create_model(
            wm.selected_account_id, wm.selected_project_id, self.model_name
        )
        wm.selected_model_id = model_id
        wm.selected_model_name = model_name
        self.report({"INFO"}, f"Created model: {model_name} -> ID: {model_id}")
        # Force redraw
        context.window.screen = context.window.screen
        context.area.tag_redraw()
        return {"FINISHED"}

    def invoke(self, context: Context, event: Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout: UILayout = self.layout
        layout.prop(self, "model_name")


def register() -> None:
    bpy.utils.register_class(SPECKLE_OT_create_model)


def unregister() -> None:
    bpy.utils.unregister_class(SPECKLE_OT_create_model)


def create_model(account_id: str, project_id: str, model_name: str) -> Tuple[str, str]:
    accounts: List[Account] = get_local_accounts()
    account: Optional[Account] = next(
        (acc for acc in accounts if acc.id == account_id), None
    )

    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)
    model = client.model.create(
        input=CreateModelInput(name=model_name, description="", project_id=project_id)
    )
    return [model.id, model.name]
