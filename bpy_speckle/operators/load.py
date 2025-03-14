import bpy
from typing import Set, Dict, Union, List, Tuple
from bpy.types import Collection, Object, Context
from specklepy.api.credentials import get_local_accounts
from specklepy.transports.server import ServerTransport
from specklepy.api import operations
from specklepy.api.client import SpeckleClient
from specklepy.objects.base import Base
from specklepy.objects.models.collections.collection import Collection as SCollection
from specklepy.objects.graph_traversal.default_traversal import (
    create_default_traversal_function,
)
from specklepy.objects.graph_traversal.traversal import TraversalContext

from ..utils.get_ascendants import get_ascendants, get_ascendant_of_type
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

    @staticmethod
    def find_or_create_blender_collection(
        name: str,
        parent_collection: Collection,
        created_collections: Dict[str, Collection],
    ) -> Collection:
        """
        Find an existing collection or create a new one with the given name

        Args:
            name: Name for the collection
            parent_collection: Parent collection to link to if creating a new collection
            created_collections: Dictionary of collections created so far (for caching)

        Returns:
            The found or created collection
        """
        # Check if we've already created this collection
        if name in created_collections:
            return created_collections[name]

        # Check if collection already exists in Blender
        if name in bpy.data.collections:
            collection = bpy.data.collections[name]
            created_collections[name] = collection

            # Make sure it's linked to parent_collection if not already
            if collection.name not in parent_collection.children:
                try:
                    parent_collection.children.link(collection)
                except RuntimeError:
                    # Collection might already be linked elsewhere
                    pass

            return collection

        # Create new collection
        collection = bpy.data.collections.new(name)
        parent_collection.children.link(collection)
        created_collections[name] = collection

        return collection

    @classmethod
    def handle_hierarchy(
        cls,
        obj: Object,
        speckle_obj: Base,
        traversal_context: TraversalContext,
        converted_objects: Dict[str, Union[Object, Collection]],
        root_collection: Collection,
        created_collections: Dict[str, Collection],
    ) -> None:
        """
        handle hierarchy for a converted object
        """
        # first check if object already has a parent or is in a collection
        if obj.parent or any(obj.name in c.objects for c in bpy.data.collections):
            # already placed in hierarchy, skip
            return

        # find parent collections in Speckle hierarchy
        parent_collections = list(get_ascendant_of_type(traversal_context, SCollection))

        if parent_collections:
            # get the nearest parent collection
            parent_speckle_collection = parent_collections[0]

            # try to find the corresponding Blender collection
            blender_collection = None

            # if collection was already converted, use it
            if parent_speckle_collection.id in converted_objects:
                parent_obj = converted_objects[parent_speckle_collection.id]
                if isinstance(parent_obj, Collection):
                    blender_collection = parent_obj

            # if not found, create a new collection using the Speckle collection name
            if not blender_collection:
                collection_name = (
                    getattr(parent_speckle_collection, "name", None)
                    or f"Collection_{parent_speckle_collection.id[:8]}"
                )
                blender_collection = cls.find_or_create_blender_collection(
                    collection_name, root_collection, created_collections
                )
                # store for future reference
                converted_objects[parent_speckle_collection.id] = blender_collection

            # link object to this collection
            try:
                blender_collection.objects.link(obj)
            except RuntimeError:
                # object might already be linked to this collection
                # maybe better error handling here?
                pass
        else:
            # no parent collections found, check for parent objects
            parent_objects = list(get_ascendants(traversal_context))

            if len(parent_objects) > 1:  # skip the current object
                parent_speckle_obj = parent_objects[1]  # get the parent

                if parent_speckle_obj.id in converted_objects:
                    parent_obj = converted_objects[parent_speckle_obj.id]

                    if isinstance(parent_obj, Object):
                        # set parent relationship
                        obj.parent = parent_obj
                    elif isinstance(parent_obj, Collection):
                        # link to parent collection
                        try:
                            parent_obj.objects.link(obj)
                        except RuntimeError:
                            # object might already be linked to this collection
                            pass
                    else:
                        # link to root collection as fallback
                        # if no parent has found
                        try:
                            root_collection.objects.link(obj)
                        except RuntimeError:
                            pass
                else:
                    # parent not converted yet, link to root collection for now
                    try:
                        root_collection.objects.link(obj)
                    except RuntimeError:
                        pass
            else:
                # no parents, link to root collection
                try:
                    root_collection.objects.link(obj)
                except RuntimeError:
                    pass

    @classmethod
    def process_deferred_parenting(
        cls,
        traversal_contexts: List[Tuple[Base, TraversalContext, Object]],
        converted_objects: Dict[str, Union[Object, Collection]],
        root_collection: Collection,
        created_collections: Dict[str, Collection],
    ) -> None:
        """
        process objects that needed to wait for their parents to be converted
        """
        for speckle_obj, context, blender_obj in traversal_contexts:
            cls.handle_hierarchy(
                blender_obj,
                speckle_obj,
                context,
                converted_objects,
                root_collection,
                created_collections,
            )

    @classmethod
    def load(cls, context: Context, model_card) -> None:
        """
        load objects from Speckle and maintain hierarchy
        """
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

        if account is None:
            print("No Speckle account found")
            return

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

        # track converted objects and their Speckle IDs
        converted_objects: Dict[str, Union[Object, Collection]] = {}
        created_collections: Dict[str, Collection] = {}
        deferred_hierarchy: List[Tuple[Base, TraversalContext, Object]] = []
        conversion_count = 0

        # first pass: Convert objects
        for traversal_item in traversal_function.traverse(version_data):
            speckle_object = traversal_item.current

            # skip if already processed
            if hasattr(speckle_object, "id") and speckle_object.id in converted_objects:
                continue

            try:
                # if this is a Speckle Collection, create a Blender collection
                if isinstance(speckle_object, SCollection):
                    collection_name = (
                        getattr(speckle_object, "name", None)
                        or f"Collection_{speckle_object.id[:8]}"
                    )
                    collection = cls.find_or_create_blender_collection(
                        collection_name, root_collection, created_collections
                    )
                    converted_objects[speckle_object.id] = collection
                    print(f"Created collection: {collection_name}")

                    # handle this collection's placement in the hierarchy
                    parent_collections = list(
                        get_ascendant_of_type(traversal_item, SCollection)
                    )
                    if parent_collections:
                        # skip the current collection itself if it's in the list
                        parent_collections = [
                            pc
                            for pc in parent_collections
                            if pc.id != speckle_object.id
                        ]

                    if parent_collections:
                        parent_collection = parent_collections[0]
                        if parent_collection.id in converted_objects:
                            parent = converted_objects[parent_collection.id]
                            if isinstance(parent, Collection):
                                # if we already have the parent collection, link this one
                                if collection.name not in parent.children:
                                    try:
                                        # unlink from previous parent first
                                        for pcoll in bpy.data.collections:
                                            if collection.name in pcoll.children:
                                                pcoll.children.unlink(collection)
                                        # link to new parent
                                        parent.children.link(collection)
                                    except RuntimeError as e:
                                        print(
                                            f"Error linking collection to parent: {e}"
                                        )
                else:
                    # convert the Speckle object to a Blender object
                    blender_obj = convert_to_native(speckle_object)
                    if blender_obj is not None:
                        # store the converted object
                        if hasattr(speckle_object, "id"):
                            converted_objects[speckle_object.id] = blender_obj

                        # save context for hierarchy processing
                        deferred_hierarchy.append(
                            (speckle_object, traversal_item, blender_obj)
                        )
                        print(f"Successfully converted: {speckle_object.speckle_type}")
                    else:
                        print(f"No converter found for: {speckle_object.speckle_type}")
            except Exception as e:
                print(f"Error converting {speckle_object.speckle_type}: {str(e)}")

            # update progress
            conversion_count += 1
            if conversion_count % 10 == 0:
                context.window_manager.progress_update(min(conversion_count, 100))

        # second pass: Process hierarchy for all objects
        cls.process_deferred_parenting(
            deferred_hierarchy, converted_objects, root_collection, created_collections
        )

        # end progress bar
        context.window_manager.progress_end()

        # select the new collection in the outliner
        for area in context.screen.areas:
            if area.type == "OUTLINER":
                area.tag_redraw()

        print(f"Load process completed. Imported {len(converted_objects)} objects.")
