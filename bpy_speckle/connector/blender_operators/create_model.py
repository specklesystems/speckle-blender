import bpy
from bpy.types import Context, Event, UILayout
from specklepy.core.api.inputs import CreateModelInput
from typing import Tuple

from ..utils.account_manager import _client_cache


class SPECKLE_OT_create_model(bpy.types.Operator):
    bl_idname = "speckle.create_model"
    bl_label = "Create Model"
    bl_description = "Create a new Speckle model"

    model_name: bpy.props.StringProperty(name="Model Name")  # type: ignore

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager

        if not self.model_name.strip():
            self.report({"ERROR"}, "Model name cannot be empty")
            return {"CANCELLED"}
        
        try:
            model_id, model_name = create_model(
                wm.selected_account_id, wm.selected_project_id, self.model_name
            )
            wm.selected_model_id = model_id
            wm.selected_model_name = model_name
            self.report({"INFO"}, f"Created model: {model_name} -> ID: {model_id}")
            # Force redraw
            context.window.screen = context.window.screen
            context.area.tag_redraw()
        except Exception as e:
            self.report({"ERROR"}, f"Failed to create model: {str(e)}")
            return {"CANCELLED"}
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
    try:
        # Get cached client
        client = _client_cache.get_client(account_id)
        if not client:
            raise ValueError(f"Could not get client for account: {account_id}")

        model = client.model.create(
            input=CreateModelInput(name=model_name, description="", project_id=project_id)
        )
        return (model.id, model.name)
    except Exception as e:
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        raise e
