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
from ...converter.to_native import convert_to_native, render_material_proxy_to_native


def load_operation(context: Context) -> None:
    """
    load objects from Speckle and maintain hierarchy.
    """

    wm = context.window_manager

    # get account
    # to discuss: this looks redundant, we need to cache it somehow
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

    # receive the data
    client = SpeckleClient(host=account.serverInfo.url)
    client.authenticate_with_account(account)

    transport = ServerTransport(stream_id=wm.selected_project_id, client=client)

    version = client.version.get(wm.selected_version_id, wm.selected_project_id)
    obj_id = version.referenced_object

    version_data = operations.receive(obj_id, transport)

    material_mapping = render_material_proxy_to_native(version_data)
    print(f"Created material mapping for {len(material_mapping)} objects")

    traversal_function = create_default_traversal_function()

    root_collection_name = f"{wm.selected_model_name} - {wm.selected_version_id[:8]}"
    root_collection = bpy.data.collections.new(root_collection_name)
    context.scene.collection.children.link(root_collection)

    context.window_manager.progress_begin(0, 100)

    # dictionary to track converted objects by Speckle ID
    converted_objects = {}
    created_collections = {}
    created_collections[root_collection_name] = root_collection

    collection_hierarchy = {}
    all_objects = {}

    speckle_root_id = None

    for traversal_item in traversal_function.traverse(version_data):
        speckle_obj = traversal_item.current

        if not hasattr(speckle_obj, "id"):
            continue

        all_objects[speckle_obj.id] = speckle_obj

        # get all ascendants in order (current to root)
        ascendants = list(get_ascendants(traversal_item))
        parent_ascendants = ascendants[1:] if len(ascendants) > 1 else []

        if isinstance(speckle_obj, SCollection):
            if not parent_ascendants and speckle_root_id is None:
                speckle_root_id = speckle_obj.id

            collection_name = getattr(
                speckle_obj, "name", f"Collection_{speckle_obj.id[:8]}"
            )

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

            # build full path hierarchy
            if parent_id in collection_hierarchy:
                collection_hierarchy[speckle_obj.id]["full_path"] = (
                    collection_hierarchy[parent_id]["full_path"] + [collection_name]
                )

        else:
            if hasattr(speckle_obj, "id"):
                parent_id = None
                for parent in parent_ascendants:
                    if isinstance(parent, SCollection) and hasattr(parent, "id"):
                        parent_id = parent.id
                        break

    def get_collection_depth(coll_id):
        parent_id = collection_hierarchy[coll_id]["parent_id"]
        if parent_id is None:
            return 0
        if parent_id not in collection_hierarchy:
            return 0
        return 1 + get_collection_depth(parent_id)

    sorted_collections = sorted(
        collection_hierarchy.keys(),
        key=lambda coll_id: (
            get_collection_depth(coll_id),
            collection_hierarchy[coll_id]["name"],
        ),
    )

    if speckle_root_id and speckle_root_id in collection_hierarchy:
        collection_hierarchy[speckle_root_id]["blender_collection"] = root_collection
        converted_objects[speckle_root_id] = root_collection

    # create collections in depth order (skip the root that's already mapped)
    for coll_id in sorted_collections:
        if coll_id == speckle_root_id:
            continue

        coll_info = collection_hierarchy[coll_id]
        coll_name = coll_info["name"]
        parent_id = coll_info["parent_id"]
        full_path = coll_info["full_path"]

        collection_key = tuple(full_path)

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

        coll_info["blender_collection"] = blender_collection
        converted_objects[coll_id] = blender_collection

    conversion_count = 0
    for traversal_item in traversal_function.traverse(version_data):
        speckle_obj = traversal_item.current

        if isinstance(speckle_obj, SCollection):
            continue

        if hasattr(speckle_obj, "id") and speckle_obj.id in converted_objects:
            continue

        try:
            blender_obj = convert_to_native(speckle_obj, material_mapping)
            if blender_obj is None:
                print(f"No converter found for: {speckle_obj.speckle_type}")
                continue

            if hasattr(speckle_obj, "id"):
                converted_objects[speckle_obj.id] = blender_obj

            target_collection = root_collection
            ascendants = list(get_ascendants(traversal_item))

            for parent in ascendants[1:] if len(ascendants) > 1 else []:
                if isinstance(parent, SCollection) and hasattr(parent, "id"):
                    parent_id = parent.id
                    if parent_id in collection_hierarchy:
                        coll_info = collection_hierarchy[parent_id]
                        if coll_info["blender_collection"]:
                            target_collection = coll_info["blender_collection"]
                            break

            try:
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

        conversion_count += 1
        if conversion_count % 10 == 0:
            context.window_manager.progress_update(min(conversion_count, 100))

    context.window_manager.progress_end()

    for area in context.screen.areas:
        if area.type == "OUTLINER":
            area.tag_redraw()

    print(f"Load process completed. Imported {len(converted_objects)} objects.")
