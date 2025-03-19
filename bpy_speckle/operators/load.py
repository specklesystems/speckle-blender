import bpy
from typing import Set
from bpy.types import Context
from specklepy.api.credentials import get_local_accounts
from specklepy.transports.server import ServerTransport
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.objects.models.collections.collection import Collection as SCollection
from specklepy.objects.graph_traversal.default_traversal import (
    create_default_traversal_function,
)

from ..utils.get_ascendants import get_ascendants
from ..converter.to_native import convert_to_native


class SPECKLE_OT_load(bpy.types.Operator):
    bl_idname = "speckle.load"
    bl_label = "Load from Speckle"
    bl_description = "Load objects from Speckle"

    def invoke(self, context: Context, event: bpy.types.Event) -> Set[str]:
        # Captures cursor position for UI placement
        context.scene.speckle_state.mouse_position = (event.mouse_x, event.mouse_y)
        return self.execute(context)

    def execute(self, context: Context) -> Set[str]:
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
    def load(cls, context: Context, model_card) -> None:
        """
        Load objects from Speckle and maintain hierarchy.
        First establish collection hierarchy, then convert and place objects.
        """

        # Get account
        account = next(
            (
                acc
                for acc in get_local_accounts()
                if acc.id == context.window_manager.selected_account_id
            ),
            None,
        )

        if account is None:
            print("No Speckle account found")
            return

        # Initialize the Speckle client
        client = SpeckleClient(host=account.serverInfo.url)
        # Authenticate with account
        client.authenticate_with_account(account)

        # Create a transport
        transport = ServerTransport(stream_id=model_card.project_id, client=client)

        # Get the version
        version = client.version.get(model_card.version_id, model_card.project_id)
        obj_id = version.referenced_object

        # Receive the data
        version_data = operations.receive(obj_id, transport)

        # Default traversal function
        traversal_function = create_default_traversal_function()

        # Create a root collection in Blender to hold all imported objects
        root_collection_name = f"{model_card.model_name} - {model_card.version_id[:8]}"
        root_collection = bpy.data.collections.new(root_collection_name)
        context.scene.collection.children.link(root_collection)

        # Start conversion process
        context.window_manager.progress_begin(0, 100)

        # Dictionary to track converted objects by Speckle ID
        converted_objects = {}
        # Dictionary to track created collections by name to avoid duplicates
        created_collections = {}
        created_collections[root_collection_name] = root_collection

        print("Creating collection hierarchy...")

        # First create a complete map of the Speckle hierarchy
        collection_hierarchy = {}
        all_objects = {}

        # Track the root collection ID from Speckle
        speckle_root_id = None

        for traversal_item in traversal_function.traverse(version_data):
            speckle_obj = traversal_item.current

            if not hasattr(speckle_obj, "id"):
                continue

            # Store all objects for later reference
            all_objects[speckle_obj.id] = speckle_obj

            # Get all ascendants in order (current to root)
            ascendants = list(get_ascendants(traversal_item))
            parent_ascendants = ascendants[1:] if len(ascendants) > 1 else []

            if isinstance(speckle_obj, SCollection):
                # Track the top-level collection (the one with no parents)
                if not parent_ascendants and speckle_root_id is None:
                    speckle_root_id = speckle_obj.id

                # Get collection name
                collection_name = getattr(
                    speckle_obj, "name", f"Collection_{speckle_obj.id[:8]}"
                )

                # Find immediate parent collection if any
                parent_id = None
                for parent in parent_ascendants:
                    if isinstance(parent, SCollection) and hasattr(parent, "id"):
                        parent_id = parent.id
                        break

                # Store collection info
                collection_hierarchy[speckle_obj.id] = {
                    "id": speckle_obj.id,
                    "name": collection_name,
                    "parent_id": parent_id,
                    "blender_collection": None,
                    "full_path": [
                        collection_name
                    ],  # Start the path with this collection
                }

                # Build full path hierarchy
                if parent_id in collection_hierarchy:
                    collection_hierarchy[speckle_obj.id]["full_path"] = (
                        collection_hierarchy[parent_id]["full_path"] + [collection_name]
                    )

            else:
                # for non-collection objects, just store their parent information
                if hasattr(speckle_obj, "id"):
                    # Find immediate parent collection
                    parent_id = None
                    for parent in parent_ascendants:
                        if isinstance(parent, SCollection) and hasattr(parent, "id"):
                            parent_id = parent.id
                            break

        # create all collections in the right order
        def get_collection_depth(coll_id):
            parent_id = collection_hierarchy[coll_id]["parent_id"]
            if parent_id is None:
                return 0
            if parent_id not in collection_hierarchy:
                return 0
            return 1 + get_collection_depth(parent_id)

        # sort collections by depth to ensure parents are created before children
        sorted_collections = sorted(
            collection_hierarchy.keys(),
            key=lambda coll_id: (
                get_collection_depth(coll_id),
                collection_hierarchy[coll_id]["name"],
            ),
        )

        # map the Speckle root collection to our Blender root collection
        if speckle_root_id and speckle_root_id in collection_hierarchy:
            collection_hierarchy[speckle_root_id]["blender_collection"] = (
                root_collection
            )
            converted_objects[speckle_root_id] = root_collection

        # create collections in depth order (skip the root that's already mapped)
        for coll_id in sorted_collections:
            # skip the root collection (already handled)
            if coll_id == speckle_root_id:
                continue

            coll_info = collection_hierarchy[coll_id]
            coll_name = coll_info["name"]
            parent_id = coll_info["parent_id"]
            full_path = coll_info["full_path"]

            # key to use for checking if collection already exists
            collection_key = tuple(full_path)

            # determine parent collection
            parent_collection = root_collection
            if parent_id and parent_id in collection_hierarchy:
                parent_info = collection_hierarchy[parent_id]
                if parent_info["blender_collection"]:
                    parent_collection = parent_info["blender_collection"]

            # create or find the collection
            if collection_key in created_collections:
                blender_collection = created_collections[collection_key]

            else:
                blender_collection = bpy.data.collections.new(coll_name)
                parent_collection.children.link(blender_collection)
                created_collections[collection_key] = blender_collection

            # store the created collection
            coll_info["blender_collection"] = blender_collection
            converted_objects[coll_id] = blender_collection

        conversion_count = 0
        for traversal_item in traversal_function.traverse(version_data):
            speckle_obj = traversal_item.current

            # skip collections (already handled)
            if isinstance(speckle_obj, SCollection):
                continue

            # skip if already processed
            if hasattr(speckle_obj, "id") and speckle_obj.id in converted_objects:
                continue

            try:
                # convert here
                blender_obj = convert_to_native(speckle_obj)
                if blender_obj is None:
                    print(f"No converter found for: {speckle_obj.speckle_type}")
                    continue

                # store the converted object
                if hasattr(speckle_obj, "id"):
                    converted_objects[speckle_obj.id] = blender_obj

                # determine which collection this object should be placed in
                target_collection = root_collection
                ascendants = list(get_ascendants(traversal_item))

                # find immediate parent collection by walking up the hierarchy
                for parent in ascendants[1:] if len(ascendants) > 1 else []:
                    if isinstance(parent, SCollection) and hasattr(parent, "id"):
                        parent_id = parent.id
                        if parent_id in collection_hierarchy:
                            coll_info = collection_hierarchy[parent_id]
                            if coll_info["blender_collection"]:
                                target_collection = coll_info["blender_collection"]
                                break

                # link object to the target collection
                try:
                    # check if already linked
                    already_linked = False
                    for coll in bpy.data.collections:
                        if blender_obj.name in coll.objects:
                            already_linked = True

                    if not already_linked:
                        target_collection.objects.link(blender_obj)

                except RuntimeError as e:
                    print(f"Error linking object to collection: {e}")

            except Exception as e:
                print(f"Error converting {speckle_obj.speckle_type}: {str(e)}")
                import traceback

                traceback.print_exc()

            # update progress
            conversion_count += 1
            if conversion_count % 10 == 0:
                context.window_manager.progress_update(min(conversion_count, 100))

        # end progress bar
        context.window_manager.progress_end()

        # select the new collection in the outliner
        for area in context.screen.areas:
            if area.type == "OUTLINER":
                area.tag_redraw()

        print(f"Load process completed. Imported {len(converted_objects)} objects.")
