import bpy
from typing import Set
from specklepy.api.credentials import get_local_accounts
from specklepy.transports.server import ServerTransport
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.objects.base import Base
from ..converter.to_native import can_convert_to_native, convert_to_native

class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        # Captures cursor position for UI placement
        context.scene.speckle_state.mouse_position = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Sets the UI mode to LOAD
        context.scene.speckle_state.ui_mode = "LOAD"
        # Logs cursor position
        self.report({'INFO'}, f"Load button clicked at {context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1]}")
        # Opens project_selection_dialog
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")

        return {'FINISHED'}
    
    @classmethod
    def load(cls, context: bpy.types.Context, model_card) -> None:

        print("Load process started")
        print(f"Loading project: {model_card.project_name}, model: {model_card.model_name}")
        print(f"Project ID: {model_card.project_id}")
        print(f"Version ID: {model_card.version_id}")

        try:
            # get the account from local accounts
            account = next((acc for acc in get_local_accounts() if acc.id == context.window_manager.selected_account_id), None)
            if not account:
                raise Exception("No Speckle account found")

            # initialize the Speckle client
            client = SpeckleClient(host=account.serverInfo.url)
            # authenticate with account
            client.authenticate_with_account(account)

            # now we need a transport
            transport = ServerTransport(
                stream_id=model_card.project_id,
                client=client
            )

            # get the version
            version = client.version.get(model_card.version_id, model_card.project_id)
            obj_id = version.referenced_object

            # receive the data
            version_data = operations.receive(
                obj_id,
                transport
            )

            # TO DISCUSS
            # create a root collection in Blender to hold all imported objects
            root_collection_name = f"{model_card.model_name} - {model_card.version_id[:8]}"
            root_collection = bpy.data.collections.new(root_collection_name)
            context.scene.collection.children.link(root_collection)
            
            # start conversion process
            context.window_manager.progress_begin(0, 100)
            
            # process and convert the received data to Blender objects
            converted_objects = {}
            traversal_queue = [version_data]
            converted_count = 0
            total_count = getattr(version_data, "totalChildrenCount", 100) or 100
            
            while traversal_queue:
                current_object = traversal_queue.pop(0)
                
                # Skip if already processed
                if hasattr(current_object, "id") and current_object.id in converted_objects:
                    continue
                
                try:
                    # check if this object can be converted
                    if can_convert_to_native(current_object):
                        # convert the object to Blender
                        blender_obj = convert_to_native(current_object)
                        
                        # store the converted object
                        if hasattr(current_object, "id"):
                            converted_objects[current_object.id] = blender_obj
                        
                        # link to the root collection if not already in a collection
                        if blender_obj.name not in root_collection.objects:
                            try:
                                root_collection.objects.link(blender_obj)
                            except RuntimeError:
                                # Object might already be linked to another collection
                                pass
                        
                        print(f"Successfully converted: {current_object.speckle_type}")
                    
                    # check for children/elements to process
                    children = []
                    # look for common element properties
                    for prop_name in ["elements", "Elements", "@elements"]:
                        if hasattr(current_object, prop_name):
                            elements = getattr(current_object, prop_name)
                            if isinstance(elements, list):
                                children.extend(elements)
                            elif isinstance(elements, Base):
                                children.append(elements)
                    
                    # add all children to the traversal queue
                    traversal_queue.extend(children)
                
                except Exception as e:
                    print(f"Error converting object: {str(e)}")
                
                # update progress
                converted_count += 1
                progress = int((converted_count / total_count) * 100)
                context.window_manager.progress_update(min(progress, 100))
            
            context.window_manager.progress_end()
            print(f"Conversion completed. Converted {converted_count} objects.")
            
        except Exception as e:
            print(f"Error loading from Speckle: {str(e)}")
            context.window_manager.progress_end()
            return