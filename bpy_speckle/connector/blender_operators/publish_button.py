import bpy
from bpy.types import Context
from bpy.types import Event
from typing import Set, List, Optional

from specklepy.objects import Base
from specklepy.objects.models.collections.collection import Collection
from specklepy.core.api import operations
from specklepy.core.api.client import SpeckleClient
from specklepy.transports.server import ServerTransport
from specklepy.core.api.inputs.version_inputs import CreateVersionInput
from specklepy.core.api.credentials import get_local_accounts
from specklepy.objects.models.units import Units

from ...converter.to_speckle import convert_to_speckle
from ...converter.to_speckle.material_to_speckle import (
    add_render_material_proxies_to_base,
)
from ...converter.utils import get_project_workspace_id
from specklepy.logging import metrics
from ....bpy_speckle import bl_info


class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"

    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager

        if not context.selected_objects and not context.active_object:
            self.report({"ERROR"}, "No objects selected to publish")
            return {"CANCELLED"}

        account_id = getattr(wm, "selected_account_id", "")
        project_id = getattr(wm, "selected_project_id", "")
        model_id = getattr(wm, "selected_model_id", "")

        if not account_id:
            self.report({"ERROR"}, "No account selected")
            return {"CANCELLED"}

        if not project_id:
            self.report({"ERROR"}, "No project selected")
            return {"CANCELLED"}

        if not model_id:
            self.report({"ERROR"}, "No model selected")
            return {"CANCELLED"}

        try:
            account = next(
                (acc for acc in get_local_accounts() if acc.id == account_id),
                None,
            )

            if account is None:
                self.report({"ERROR"}, "No Speckle account found")
                return {"CANCELLED"}

            client = SpeckleClient(host=account.serverInfo.url)
            client.authenticate_with_account(account)

            transport = ServerTransport(stream_id=project_id, client=client)

            # get objects to convert
            objects_to_convert = context.selected_objects or [context.active_object]
            speckle_objects = self.convert_selected_objects(context)

            if not speckle_objects:
                self.report(
                    {"ERROR"}, "No objects could be converted to Speckle format"
                )
                return {"CANCELLED"}

            # get the Blender file name to set the name
            file_name = bpy.path.basename(bpy.data.filepath)
            collection_name = file_name if file_name else "Untitled.blend"

            # create a collection to hold all objects
            collection = Collection(name=collection_name)
            collection.units = Units.m.value
            collection["version"] = 3

            for obj in speckle_objects:
                if obj is not None:
                    collection.elements.append(obj)

            add_render_material_proxies_to_base(collection, objects_to_convert)

            obj_id = operations.send(collection, [transport])

            version_input = CreateVersionInput(
                objectId=obj_id,
                modelId=model_id,
                projectId=project_id,
                message="",
                sourceApplication="blender",
            )

            version = client.version.create(version_input)
            version_id = version.id

            metrics.set_host_app("blender")

            metrics.track(
                metrics.SEND,
                account,
                {
                    "ui": "dui3",
                    "hostAppVersion": ",".join(map(str, bl_info["blender"])),
                    "core_version": ",".join(map(str, bl_info["version"])),
                    "workspace_id": get_project_workspace_id(client, project_id),
                },
            )

            # Update model card if needed
            if hasattr(context.scene, "speckle_state") and hasattr(
                context.scene.speckle_state, "model_cards"
            ):
                model_card = context.scene.speckle_state.model_cards.add()
                model_card.account_id = account_id
                model_card.server_url = account.serverInfo.url
                model_card.project_id = project_id
                model_card.project_name = getattr(wm, "selected_project_name", "")
                model_card.model_id = model_id
                model_card.model_name = getattr(wm, "selected_model_name", "")
                model_card.is_publish = True
                model_card.load_option = "SPECIFIC"  # Published versions are specific
                model_card.version_id = version_id
                model_card.collection_name = (
                    f"{getattr(wm, 'selected_model_name', 'Model')} - {version_id[:8]}"
                )

            # Clear selected model details from Window Manager AFTER creating model card
            wm.selected_account_id = ""
            wm.selected_project_id = ""
            wm.selected_project_name = ""
            wm.selected_model_id = ""
            wm.selected_model_name = ""
            wm.selected_version_load_option = ""
            wm.selected_version_id = ""

            self.report(
                {"INFO"},
                f"Successfully published {len(speckle_objects)} objects to Speckle with materials",
            )
            return {"FINISHED"}

        except Exception as e:
            self.report({"ERROR"}, f"Failed to publish: {str(e)}")
            import traceback

            traceback.print_exc()
            return {"CANCELLED"}

    def convert_selected_objects(self, context: Context) -> List[Optional[Base]]:
        scene = context.scene
        unit_settings = scene.unit_settings

        # get units from Blender's unit system
        if unit_settings.system == "METRIC":
            if unit_settings.length_unit == "METERS":
                units = Units.m
            elif unit_settings.length_unit == "CENTIMETERS":
                units = Units.cm
            elif unit_settings.length_unit == "MILLIMETERS":
                units = Units.mm
            elif unit_settings.length_unit == "KILOMETERS":
                units = Units.km
            else:
                units = Units.m
        elif unit_settings.system == "IMPERIAL":
            if unit_settings.length_unit == "FEET":
                units = Units.feet
            elif unit_settings.length_unit == "INCHES":
                units = Units.inches
            elif unit_settings.length_unit == "YARDS":
                units = Units.yards
            elif unit_settings.length_unit == "MILES":
                units = Units.miles
            else:
                units = Units.feet  # default to feet
        else:
            units = Units.m  # default to meters

        scale_factor = unit_settings.scale_length

        # convert each selected object
        speckle_objects = []
        objects_to_convert = context.selected_objects or [context.active_object]
        for obj in objects_to_convert:
            # Skip objects that are not supported
            if not obj or obj.type not in ["MESH", "CURVE", "EMPTY"]:
                continue

            # convert the object
            speckle_obj = convert_to_speckle(obj, scale_factor, units.value)
            if speckle_obj:
                speckle_objects.append(speckle_obj)

        return speckle_objects
