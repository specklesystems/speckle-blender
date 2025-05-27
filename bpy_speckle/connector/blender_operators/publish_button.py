import bpy
from bpy.types import Context
from bpy.types import Event
from typing import Set, List, Optional

from specklepy.objects import Base
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.transports.server import ServerTransport
from specklepy.core.api.inputs.version_inputs import CreateVersionInput
from specklepy.api.credentials import get_local_accounts

from ...converter.to_speckle import convert_to_speckle
from ...converter.to_speckle.material_to_speckle import add_render_material_proxies_to_base


class SPECKLE_OT_publish(bpy.types.Operator):
    bl_idname = "speckle.publish"

    bl_label = "Publish to Speckle"
    bl_description = "Publish selected objects to Speckle"

    def invoke(self, context: Context, event: Event) -> Set[str]:
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
        wm = context.window_manager
        
        # Check if there's a selection in the scene
        if not context.selected_objects and not context.active_object:
            self.report({"ERROR"}, "No objects selected to publish")
            return {"CANCELLED"}
        
        # Get selected account, project and model from window manager
        account_id = getattr(wm, "selected_account_id", "")
        project_id = getattr(wm, "selected_project_id", "")
        model_id = getattr(wm, "selected_model_id", "")
        
        # Check that we have the required information
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
            # Get account using the same approach as load_operation
            account = next(
                (
                    acc
                    for acc in get_local_accounts()
                    if acc.id == account_id
                ),
                None,
            )

            if account is None:
                self.report({"ERROR"}, "No Speckle account found")
                return {"CANCELLED"}
            
            # Initialize the Speckle client - same approach as load_operation
            client = SpeckleClient(host=account.serverInfo.url)
            client.authenticate_with_account(account)
            
            # Create a server transport
            transport = ServerTransport(stream_id=project_id, client=client)
            
            # Get objects to convert (keep reference to original Blender objects)
            objects_to_convert = context.selected_objects or [context.active_object]
            
            # Convert selected objects to Speckle
            speckle_objects = self.convert_selected_objects(context)
            
            if not speckle_objects:
                self.report({"ERROR"}, "No objects could be converted to Speckle format")
                return {"CANCELLED"}
            
            # Create a Base object to hold all objects
            base = Base()
            base.units = context.scene.unit_settings.system.lower()
            
            # Add objects to the base
            for i, obj in enumerate(speckle_objects):
                if obj is not None:
                    base[f"obj_{i}"] = obj
            
            # Add render material proxies to the base
            add_render_material_proxies_to_base(base, objects_to_convert)
            
            # Send the base object to Speckle
            obj_id = operations.send(base, [transport])
            
            # Create a version input
            version_input = CreateVersionInput(
                objectId=obj_id,
                modelId=model_id,
                projectId=project_id,
                message="Published from Blender",
                sourceApplication="Blender"
            )
            
            # Create the version
            version_id = client.version.create(version_input)  # noqa: F841
            
            # Clear selected model details from Window Manager
            wm.selected_account_id = ""
            wm.selected_project_id = ""
            wm.selected_project_name = ""
            wm.selected_model_id = ""
            wm.selected_model_name = ""
            wm.selected_version_load_option = ""
            wm.selected_version_id = ""
            
            # Update model card if needed
            if hasattr(context.scene, "speckle_state") and hasattr(context.scene.speckle_state, "model_cards"):
                model_card = context.scene.speckle_state.model_cards.add()
                model_card.account_id = account_id
                model_card.server_url = account.serverInfo.url
                model_card.project_id = project_id
                model_card.project_name = getattr(wm, "selected_project_name", "")
                model_card.model_id = model_id
                model_card.model_name = getattr(wm, "selected_model_name", "")
                model_card.is_publish = True
                model_card.version_id = version_id
            
            self.report({"INFO"}, f"Successfully published {len(speckle_objects)} objects to Speckle with materials")
            return {"FINISHED"}
            
        except Exception as e:
            self.report({"ERROR"}, f"Failed to publish: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
    
    def convert_selected_objects(self, context: Context) -> List[Optional[Base]]:
        """
        Convert selected objects to Speckle objects
        """
        # Get unit scale for conversion
        scene = context.scene
        unit_settings = scene.unit_settings
        
        # Determine scale factor based on unit system
        unit_system = unit_settings.system.lower()
        # Default to meters if unit system not recognized
        units = "m" if unit_system not in ["metric", "imperial"] else unit_system
        # Apply the Blender scene's unit scale
        scale_factor = unit_settings.scale_length
        
        # Convert each selected object
        speckle_objects = []
        objects_to_convert = context.selected_objects or [context.active_object]
        for obj in objects_to_convert:
            # Skip objects that are not supported
            if not obj or obj.type not in ['MESH', 'CURVE', 'EMPTY']:
                continue
                
            # Convert the object
            speckle_obj = convert_to_speckle(obj, scale_factor, units)
            if speckle_obj:
                speckle_objects.append(speckle_obj)
        
        return speckle_objects