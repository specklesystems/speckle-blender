import bpy
from bpy.types import Context
from specklepy.core.api.credentials import get_local_accounts
from specklepy.transports.server import ServerTransport
from specklepy.core.api import operations
from specklepy.core.api.client import SpeckleClient
from specklepy.objects.models.collections.collection import Collection as SCollection
from specklepy.objects.graph_traversal.default_traversal import (
    create_default_traversal_function,
)
from specklepy.core.api import host_applications

from ..utils.get_ascendants import get_ascendants
from ...converter.utils import find_object_by_id
from ...converter.to_native import (
    convert_to_native,
    render_material_proxy_to_native,
    instance_definition_proxy_to_native,
    find_instance_definitions,
)
from specklepy.logging import metrics


def load_operation(context: Context) -> None:
    """
    load objects from Speckle and maintain hierarchy.
    """
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

    version_data = operations.receive(obj_id, transport)

    metrics.set_host_app("blender")

    metrics.track(
        metrics.RECEIVE,
        account,
        {
            "ui": "dui3",
            "hostAppVersion": "3.0.0",  # TODO: get dynamic version
            "sourceHostApp": host_applications.get_host_app_from_string(
                version.source_application
            ).slug,
            "isMultiplayer": version.author_user.id != account.userInfo.id,
        },
    )

    # Create material mapping first
    material_mapping = render_material_proxy_to_native(version_data)

    definition_collections, definition_objects = instance_definition_proxy_to_native(
        version_data, material_mapping
    )

    definitions_root_collection = None
    if definition_collections:
        definitions_root_collection = bpy.data.collections.new("InstanceDefinitions")

        for collection in definition_collections.values():
            definitions_root_collection.children.link(collection)

    definition_object_ids = set()
    for definition in find_instance_definitions(version_data).values():
        definition_object_ids.update(definition.objects)
        for obj_id in definition.objects:
            found_obj = find_object_by_id(version_data, obj_id)
            if found_obj:
                if hasattr(found_obj, "id"):
                    definition_object_ids.add(found_obj.id)
                if hasattr(found_obj, "applicationId"):
                    definition_object_ids.add(found_obj.applicationId)

    traversal_function = create_default_traversal_function()

    root_collection_name = f"{wm.selected_model_name} - {wm.selected_version_id[:8]}"
    root_collection = bpy.data.collections.new(root_collection_name)
    context.scene.collection.children.link(root_collection)

    context.window_manager.progress_begin(0, 100)

    converted_objects = definition_objects.copy()

    created_collections = {}
    created_collections[root_collection_name] = root_collection

    collection_hierarchy = {}
    all_objects = {}

    speckle_root_id = None

    for traversal_item in traversal_function.traverse(version_data):
        speckle_obj = traversal_item.current

        # Skip objects that are part of instance definitions
        if speckle_obj.id in definition_object_ids or (
            hasattr(speckle_obj, "applicationId")
            and speckle_obj.applicationId in definition_object_ids
        ):
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

            if parent_id in collection_hierarchy:
                collection_hierarchy[speckle_obj.id]["full_path"] = (
                    collection_hierarchy[parent_id]["full_path"] + [collection_name]
                )

        else:
            pass

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

        if collection_key in created_collections:
            print(f"Collection already exists: {coll_name}")
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

        if not hasattr(speckle_obj, "id"):
            print("Skipping object without ID")
            continue

        # Skip objects that are part of instance definitions
        if speckle_obj.id in definition_object_ids or (
            hasattr(speckle_obj, "applicationId")
            and speckle_obj.applicationId in definition_object_ids
        ):
            continue

        if speckle_obj.id in converted_objects:
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
                            break

            blender_obj = convert_to_native(
                speckle_obj,
                material_mapping,
                definition_collections=definition_collections,
                root_collection=target_collection,
            )

            if blender_obj is None:
                continue

            converted_objects[speckle_obj.id] = blender_obj
            if hasattr(speckle_obj, "applicationId"):
                converted_objects[speckle_obj.applicationId] = blender_obj

            if not isinstance(blender_obj, bpy.types.Collection):
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

    print(f"\nLoad process completed. Imported {len(converted_objects)} objects.")
