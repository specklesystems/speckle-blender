import bpy
from typing import Set, Dict, Union
from bpy.types import Collection, Object
from specklepy.api.credentials import get_local_accounts
from specklepy.transports.server import ServerTransport
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.objects.graph_traversal.default_traversal import (
    create_default_traversal_function,
)

# from ..utils.get_ascendants import get_ascendants, get_ascendant_of_type
from ..converter.to_native import convert_to_native


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
        self.report(
            {"INFO"},
            f"Load button clicked at {context.scene.speckle_state.mouse_position[0], context.scene.speckle_state.mouse_position[1]}",
        )
        # Opens project_selection_dialog
        bpy.ops.speckle.project_selection_dialog("INVOKE_DEFAULT")

        return {"FINISHED"}

    @classmethod
    def load(cls, context: bpy.types.Context, model_card) -> None:
        print("Load process started")
        print(
            f"Loading project: {model_card.project_name}, model: {model_card.model_name}"
        )
        print(f"Project ID: {model_card.project_id}")
        print(f"Version ID: {model_card.version_id}")

        # get account
        account = next(
            (
                acc
                for acc in get_local_accounts()
                if acc.id == context.window_manager.selected_account_id
            ),
            None,
        )

        # initialize the Speckle client
        client = SpeckleClient(host=account.serverInfo.url)
        # authenticate with account
        client.authenticate_with_account(account)

        # now we need a transport
        transport = ServerTransport(stream_id=model_card.project_id, client=client)

        # get the version
        version = client.version.get(model_card.version_id, model_card.project_id)
        obj_id = version.referenced_object

        # receive the data
        version_data = operations.receive(obj_id, transport)

        # default traversal function
        traversal_function = create_default_traversal_function()

        # create a root collection in Blender to hold all imported objects
        root_collection_name = f"{model_card.model_name} - {model_card.version_id[:8]}"
        root_collection = bpy.data.collections.new(root_collection_name)
        context.scene.collection.children.link(root_collection)

        # start conversion process
        context.window_manager.progress_begin(0, 100)

        # process and convert the received data to Blender objects
        converted_objects: Dict[str, Union[Object, Collection]] = {}
        conversion_count = 0

        for obj in traversal_function.traverse(version_data):
            speckle_object = obj.current

            # Skip if already processed
            if hasattr(speckle_object, "id") and speckle_object.id in converted_objects:
                continue

            try:
                # Attempt conversion
                blender_obj = convert_to_native(speckle_object)
                if blender_obj is not None:
                    # store the converted object
                    if hasattr(speckle_object, "id"):
                        converted_objects[speckle_object.id] = blender_obj

                    # link to the root collection if not already in a collection
                    if blender_obj.name not in root_collection.objects:
                        try:
                            root_collection.objects.link(blender_obj)
                        except RuntimeError:
                            # Object might already be linked to another collection
                            pass

                    print(f"Successfully converted: {speckle_object.speckle_type}")
                else:
                    print(f"No converter found for: {speckle_object.speckle_type}")
            except Exception as e:
                print(f"Error converting {speckle_object.speckle_type}: {str(e)}")

            # Update progress
            conversion_count += 1
            if conversion_count % 10 == 0:  # Update every 10 objects to avoid slowdowns
                context.window_manager.progress_update(min(conversion_count, 100))

        # End progress bar
        context.window_manager.progress_end()

        # Select the new collection in the outliner
        for area in context.screen.areas:
            if area.type == "OUTLINER":
                area.tag_redraw()
