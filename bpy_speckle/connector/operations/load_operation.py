import bpy
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
from ...converter.utils import find_object_by_id
from ...converter.to_native import (
    convert_to_native,
    render_material_proxy_to_native,
    instance_definition_proxy_to_native,
    find_instance_definitions,
)


def print_object_locations(obj_name: str):
    """Debug helper to find all collections containing an object"""
    print(f"\n=== Checking locations of object: {obj_name} ===")
    for collection in bpy.data.collections:
        if obj_name in collection.objects:
            print(f"Found in collection: {collection.name}")


def load_operation(context: Context) -> None:
    """
    load objects from Speckle and maintain hierarchy.
    """
    print("\n=== Starting load_operation ===")
    wm = context.window_manager

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

    print(f"Using account: {account.userInfo.email}")

    # receive the data
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)

    transport = ServerTransport(stream_id=wm.selected_project_id, client=client)

    version = client.version.get(wm.selected_version_id, wm.selected_project_id)
    obj_id = version.referenced_object
    print(f"Loading object with ID: {obj_id}")

    version_data = operations.receive(obj_id, transport)

    # Create material mapping first
    print("\n=== Processing Materials ===")
    material_mapping = render_material_proxy_to_native(version_data)
    print(f"Created material mapping for {len(material_mapping)} objects")

    # Process instance definitions before regular geometry
    print("\n=== Processing Instance Definitions ===")
    definition_collections, definition_objects = instance_definition_proxy_to_native(
        version_data, material_mapping
    )
    print(f"Processed {len(definition_collections)} definition collections")
    print(f"Converted {len(definition_objects)} definition objects")

    # Create a hidden collection for instance definitions if we have any
    definitions_root_collection = None
    if definition_collections:
        print("\n=== Setting up Instance Definitions Collection ===")
        definitions_root_collection = bpy.data.collections.new("InstanceDefinitions")
        definitions_root_collection.hide_viewport = True
        definitions_root_collection.hide_render = True
        context.scene.collection.children.link(definitions_root_collection)

        # Link all definition collections to the hidden collection
        for collection in definition_collections.values():
            definitions_root_collection.children.link(collection)

    # Collect all object IDs that should be skipped (from definitions)
    print("\n=== Collecting Definition Object IDs ===")
    definition_object_ids = set()
    for definition in find_instance_definitions(version_data).values():
        print(f"\nFound definition: {getattr(definition, 'name', 'unnamed')}")
        if hasattr(definition, "objects"):
            if isinstance(definition.objects, list):
                print(f"Adding object references: {definition.objects}")
                definition_object_ids.update(definition.objects)  # Add reference IDs
                # Find actual objects and add their IDs too
                for obj_id in definition.objects:
                    found_obj = find_object_by_id(version_data, obj_id)
                    if found_obj:
                        if hasattr(found_obj, "id"):
                            print(f"Adding regular ID: {found_obj.id}")
                            definition_object_ids.add(found_obj.id)
                        if hasattr(found_obj, "applicationId"):
                            print(f"Adding applicationId: {found_obj.applicationId}")
                            definition_object_ids.add(found_obj.applicationId)

    print(f"\nTotal definition object IDs to skip: {len(definition_object_ids)}")
    print("Definition object IDs:", definition_object_ids)

    print("\n=== Starting Regular Object Processing ===")
    traversal_function = create_default_traversal_function()

    root_collection_name = f"{wm.selected_model_name} - {wm.selected_version_id[:8]}"
    print(f"Creating root collection: {root_collection_name}")
    root_collection = bpy.data.collections.new(root_collection_name)
    context.scene.collection.children.link(root_collection)

    context.window_manager.progress_begin(0, 100)

    # Use the objects from definitions as base for tracking converted objects
    converted_objects = definition_objects.copy()
    print(f"Starting with {len(converted_objects)} pre-converted objects")

    created_collections = {}
    created_collections[root_collection_name] = root_collection

    collection_hierarchy = {}
    all_objects = {}

    speckle_root_id = None

    print("\n=== First Pass: Building Collection Hierarchy ===")
    for traversal_item in traversal_function.traverse(version_data):
        speckle_obj = traversal_item.current

        if not hasattr(speckle_obj, "id"):
            print("Skipping object without ID")
            continue

        # Skip objects that are part of instance definitions
        if speckle_obj.id in definition_object_ids or (
            hasattr(speckle_obj, "applicationId")
            and speckle_obj.applicationId in definition_object_ids
        ):
            print(f"Skipping definition object: {speckle_obj.id}")
            print(f"(applicationId: {getattr(speckle_obj, 'applicationId', 'none')})")
            continue

        all_objects[speckle_obj.id] = speckle_obj

        # get all ascendants in order (current to root)
        ascendants = list(get_ascendants(traversal_item))
        parent_ascendants = ascendants[1:] if len(ascendants) > 1 else []

        if isinstance(speckle_obj, SCollection):
            if not parent_ascendants and speckle_root_id is None:
                print(f"Found root collection: {speckle_obj.id}")
                speckle_root_id = speckle_obj.id

            collection_name = getattr(
                speckle_obj, "name", f"Collection_{speckle_obj.id[:8]}"
            )
            print(f"Processing collection: {collection_name}")

            parent_id = None
            for parent in parent_ascendants:
                if isinstance(parent, SCollection) and hasattr(parent, "id"):
                    parent_id = parent.id
                    break

            collection_hierarchy[speckle_obj.id] = {
                "id": speckle_obj.id,
                "name": collection_name,
                "parent_id": parent_id,
                "blender_collection": None,
                "full_path": [collection_name],
            }

            if parent_id in collection_hierarchy:
                collection_hierarchy[speckle_obj.id]["full_path"] = (
                    collection_hierarchy[parent_id]["full_path"] + [collection_name]
                )

        else:
            print(f"Found object: {speckle_obj.speckle_type} ({speckle_obj.id})")

    def get_collection_depth(coll_id):
        parent_id = collection_hierarchy[coll_id]["parent_id"]
        if parent_id is None:
            return 0
        if parent_id not in collection_hierarchy:
            return 0
        return 1 + get_collection_depth(parent_id)

    print("\n=== Creating Collection Structure ===")
    sorted_collections = sorted(
        collection_hierarchy.keys(),
        key=lambda coll_id: (
            get_collection_depth(coll_id),
            collection_hierarchy[coll_id]["name"],
        ),
    )

    if speckle_root_id and speckle_root_id in collection_hierarchy:
        print("Setting up root collection")
        collection_hierarchy[speckle_root_id]["blender_collection"] = root_collection
        converted_objects[speckle_root_id] = root_collection

    # create collections in depth order (skip the root that's already mapped)
    for coll_id in sorted_collections:
        if coll_id == speckle_root_id:
            continue

        coll_info = collection_hierarchy[coll_id]
        print(f"\nProcessing collection: {coll_info['name']}")
        coll_name = coll_info["name"]
        parent_id = coll_info["parent_id"]
        full_path = coll_info["full_path"]

        collection_key = tuple(full_path)

        parent_collection = root_collection
        if parent_id and parent_id in collection_hierarchy:
            parent_info = collection_hierarchy[parent_id]
            if parent_info["blender_collection"]:
                parent_collection = parent_info["blender_collection"]
                print(f"Using parent collection: {parent_collection.name}")

        if collection_key in created_collections:
            print(f"Collection already exists: {coll_name}")
            blender_collection = created_collections[collection_key]
        else:
            print(f"Creating new collection: {coll_name}")
            blender_collection = bpy.data.collections.new(coll_name)
            parent_collection.children.link(blender_collection)
            created_collections[collection_key] = blender_collection

        coll_info["blender_collection"] = blender_collection
        converted_objects[coll_id] = blender_collection

    print("\n=== Second Pass: Converting Objects ===")
    conversion_count = 0
    for traversal_item in traversal_function.traverse(version_data):
        speckle_obj = traversal_item.current

        if isinstance(speckle_obj, SCollection):
            print(
                f"Skipping collection in second pass: {getattr(speckle_obj, 'name', 'unnamed')}"
            )
            continue

        if not hasattr(speckle_obj, "id"):
            print("Skipping object without ID")
            continue

        # Debug object processing
        print(f"\nProcessing object: {speckle_obj.id}")
        print(f"Type: {speckle_obj.speckle_type}")

        # Skip objects that are part of instance definitions
        if speckle_obj.id in definition_object_ids or (
            hasattr(speckle_obj, "applicationId")
            and speckle_obj.applicationId in definition_object_ids
        ):
            print(f"Skipping definition object: {speckle_obj.id}")
            print(f"(applicationId: {getattr(speckle_obj, 'applicationId', 'none')})")
            continue

        if speckle_obj.id in converted_objects:
            print(f"Object already converted: {speckle_obj.id}")
            continue

        try:
            target_collection = root_collection
            ascendants = list(get_ascendants(traversal_item))

            for parent in ascendants[1:] if len(ascendants) > 1 else []:
                if isinstance(parent, SCollection) and hasattr(parent, "id"):
                    parent_id = parent.id
                    if parent_id in collection_hierarchy:
                        coll_info = collection_hierarchy[parent_id]
                        if coll_info["blender_collection"]:
                            target_collection = coll_info["blender_collection"]
                            print(f"Found target collection: {target_collection.name}")
                            break

            print(f"Converting object: {speckle_obj.id}")
            blender_obj = convert_to_native(
                speckle_obj,
                material_mapping,
                definition_collections=definition_collections,
                root_collection=target_collection,
            )

            if blender_obj is None:
                print(f"No converter found for: {speckle_obj.speckle_type}")
                continue

            print(f"Successfully converted to: {blender_obj.name}")
            # Store object by all its identifiers
            converted_objects[speckle_obj.id] = blender_obj
            if hasattr(speckle_obj, "applicationId"):
                converted_objects[speckle_obj.applicationId] = blender_obj

            # Only link non-collection objects to their target collection
            # Instance collections will be linked by the convert_to_native function
            if not isinstance(blender_obj, bpy.types.Collection):
                try:
                    print(f"Linking {blender_obj.name} to {target_collection.name}")
                    already_linked = False
                    for coll in bpy.data.collections:
                        if blender_obj.name in coll.objects:
                            print(f"Object already linked to: {coll.name}")
                            already_linked = True

                    if not already_linked:
                        target_collection.objects.link(blender_obj)
                        print("Successfully linked object")

                except RuntimeError as e:
                    print(f"Error linking object to collection: {e}")

        except Exception as e:
            print(f"Error converting {speckle_obj.speckle_type}: {str(e)}")
            import traceback

            traceback.print_exc()

        conversion_count += 1
        if conversion_count % 10 == 0:
            context.window_manager.progress_update(min(conversion_count, 100))

    context.window_manager.progress_end()

    print("\n=== Final Cleanup and Checks ===")
    for area in context.screen.areas:
        if area.type == "OUTLINER":
            area.tag_redraw()

    print("\n=== Checking Final Object Locations ===")
    # Check locations of specific objects we know about
    for obj in bpy.data.objects:
        print_object_locations(obj.name)

    print(f"\nLoad process completed. Imported {len(converted_objects)} objects.")
