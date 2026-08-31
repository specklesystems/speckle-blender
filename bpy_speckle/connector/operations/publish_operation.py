import bpy
from bpy.types import Context, Collection as BlenderCollection
from typing import List, Optional, Dict, Tuple

from specklepy.objects import Base
from specklepy.objects.models.collections.collection import Collection
from specklepy.api import operations
from specklepy.transports.server import ServerTransport
from specklepy.api.inputs.version_inputs import CreateVersionInput
from specklepy.objects.models.units import Units
from specklepy.logging.exceptions import GraphQLException, WorkspacePermissionException
from specklepy.api.inputs.model_ingestion_inputs import (
    ModelIngestionCreateInput,
    ModelIngestionStartProcessingInput,
    ModelIngestionSuccessInput,
    ModelIngestionFailedInput,
    SourceDataInput,
)

from ...converter.to_speckle import convert_to_speckle
from ...converter.to_speckle.instance_unpacker import (
    InstanceUnpackResult,
    unpack_instances,
)
from ...converter.to_speckle.material_to_speckle import (
    add_render_material_proxies_to_base,
)
from ...converter.to_speckle.metaball_unpacker import (
    MetaballUnpackResult,
    unpack_metaballs,
)
from ...converter.to_speckle.utils import get_object_id
from ...converter.utils import get_project_workspace_id
from ..utils.account_manager import _client_cache
from .bundle_publish import (
    fetch_pre_allocated_version_id,
    is_bundle_send_available,
    publish_bundle,
)
from specklepy.logging import metrics
from ... import ADDON_INFO


# Object types with a conversion path. Anything else is skipped silently — the
# selection dialog's icon map is a generic Blender-type table, not this list.
SUPPORTED_OBJECT_TYPES = frozenset(
    {"MESH", "CURVE", "SURFACE", "FONT", "EMPTY", "META"}
)


def _check_use_model_ingestion_send(client, project_id: str, model_id: str) -> bool:
    """Check if the server supports model ingestion and the user is authorized."""
    try:
        result = client.model.can_create_model_ingestion(project_id, model_id)
        result.ensure_authorised()
        return True
    except GraphQLException:
        return False


def _build_source_data() -> SourceDataInput:
    """Build data input for model ingestion."""
    file_name = bpy.path.basename(bpy.data.filepath)
    if not file_name:
        file_name = "Untitled.blend"

    file_size_bytes: Optional[int] = None
    if bpy.data.filepath:
        import os

        try:
            file_size_bytes = os.path.getsize(bpy.data.filepath)
        except OSError:
            pass

    blender_version = ".".join(map(str, ADDON_INFO["blender"]))
    return SourceDataInput(
        source_application_slug="blender",
        source_application_version=blender_version,
        file_name=file_name,
        file_size_bytes=file_size_bytes,
    )


def _send_via_ingestion(
    client,
    project_id: str,
    model_id: str,
    root_collection: Collection,
    version_message: str,
) -> str:
    """Send via the model ingestion. Returns version_id.

    Called with ``root_collection`` already converted: the ingestion is created
    here, after conversion, because the only thing that needs its pre-allocated
    version id is the bundle write (the id names the parquet files). Creating it
    this late also means a scene that converts to nothing never leaves an
    orphaned in-progress ingestion behind.

    When the bundle producer or the server's v2 data endpoints are unavailable,
    falls back to the classic ``operations.send`` + ``complete`` flow.
    """
    source_data = _build_source_data()

    create_input = ModelIngestionCreateInput(
        project_id=project_id,
        model_id=model_id,
        source_data=source_data,
        progress_message="Model ingestion created",
    )
    ingestion = client.model_ingestion.create(create_input)
    ingestion_id = ingestion.id

    try:
        start_input = ModelIngestionStartProcessingInput(
            project_id=project_id,
            ingestion_id=ingestion_id,
            progress_message="Processing model ingestion",
            source_data=source_data,
        )
        client.model_ingestion.start_processing(start_input)

        if is_bundle_send_available():
            pre_allocated_version_id = fetch_pre_allocated_version_id(
                client.account, project_id, ingestion_id
            )
            if pre_allocated_version_id:
                # the v2 upload's `complete` call creates the version itself;
                # no model_ingestion.complete follows.
                print(
                    "[Speckle] Publishing via parquet bundle "
                    f"(version {pre_allocated_version_id})"
                )
                return publish_bundle(
                    client.account,
                    project_id,
                    ingestion_id,
                    pre_allocated_version_id,
                    root_collection,
                )
            print(
                "[Speckle] Server has no pre-allocated version id — "
                "falling back to classic send"
            )

        # classic path: detached-object JSON send, then complete the ingestion
        transport = ServerTransport(stream_id=project_id, client=client)
        obj_id = operations.send(root_collection, [transport])

        success_input = ModelIngestionSuccessInput(
            project_id=project_id,
            ingestion_id=ingestion_id,
            root_object_id=obj_id,
            version_message=version_message,
        )
        version_id = client.model_ingestion.complete(success_input)
        return version_id
    except Exception as e:
        try:
            fail_input = ModelIngestionFailedInput(
                project_id=project_id,
                ingestion_id=ingestion_id,
                error_reason=str(e) or "Failed during processing",
            )
            client.model_ingestion.fail_with_error(fail_input)
        except Exception:
            pass
        raise


def _send_via_version_create(
    client,
    project_id: str,
    model_id: str,
    obj_id: str,
    version_message: str,
) -> str:
    """Send via the legacy version.create() flow. Returns version_id."""
    version_input = CreateVersionInput(
        objectId=obj_id,
        modelId=model_id,
        projectId=project_id,
        message=version_message,
        sourceApplication="blender",
    )
    version = client.version.create(version_input)
    return version.id


def publish_operation(
    context: Context,
    objects_to_convert: List,
    version_message: str = "",
    apply_modifiers: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    publish objects to speckle

    ``version_message`` has no UI: the default bundle path cannot carry one
    (the v2 ``complete`` payload has no message field), so the input was
    removed rather than silently dropped. The parameter stays because the two
    fallback paths do honour it, and it is the reconnection point if the
    server gap closes.
    """
    wm = context.window_manager

    try:
        # get cached client
        client = _client_cache.get_client(wm.selected_account_id)
        if not client:
            return False, "No Speckle client found", None

        project_id = wm.selected_project_id
        model_id = wm.selected_model_id

        # check ingestion support before sending data (fail fast on permission errors)
        use_ingestion = _check_use_model_ingestion_send(client, project_id, model_id)

        # build collection hierarchy and convert objects
        root_collection = build_collection_hierarchy(
            context, objects_to_convert, apply_modifiers
        )

        if not root_collection:
            return False, "No objects could be converted to Speckle format", None

        if use_ingestion:
            version_id = _send_via_ingestion(
                client, project_id, model_id, root_collection, version_message
            )
        else:
            transport = ServerTransport(stream_id=project_id, client=client)
            obj_id = operations.send(root_collection, [transport])
            version_id = _send_via_version_create(
                client, project_id, model_id, obj_id, version_message
            )

        # Get account for metrics tracking
        from specklepy.api.credentials import get_local_accounts

        account = next(
            (acc for acc in get_local_accounts() if acc.id == wm.selected_account_id),
            None,
        )

        if account:
            # track metrics
            metrics.set_host_app("blender")
            metrics.track(
                metrics.SEND,
                account,
                {
                    "ui": "dui3",
                    "hostAppVersion": ".".join(map(str, ADDON_INFO["blender"])),
                    "core_version": ".".join(map(str, ADDON_INFO["version"])),
                    "workspace_id": get_project_workspace_id(client, project_id),
                },
            )

        # count total objects for success message
        total_objects = count_objects_in_collection(root_collection)

        return (
            True,
            f"Successfully published {total_objects} objects with hierarchy to Speckle",
            version_id,
        )

    except WorkspacePermissionException as e:
        return False, f"Permission denied: {str(e)}", None

    except Exception as e:
        import traceback

        traceback.print_exc()
        # Clear cache on error to prevent stale clients
        _client_cache.clear()
        return False, f"Failed to publish: {str(e)}", None


def build_collection_hierarchy(
    context: Context, objects_to_convert: List, apply_modifiers: bool = True
) -> Optional[Collection]:
    """
    build a speckle collection hierarchy that mimicks blender's collection structure
    """
    # set name for root collection
    file_name = bpy.path.basename(bpy.data.filepath)
    collection_name = file_name if file_name else "Untitled.blend"

    # Collection instances expand the publish set: the members of an instanced
    # collection have to convert too, even when the user only picked the empty.
    scene_units = get_scene_units(context.scene)
    instances = unpack_instances(
        objects_to_convert,
        scene_units.value,
        context.scene.unit_settings.scale_length,
    )
    objects_to_convert = instances.objects

    # Metaball families are resolved after instancing, because a definition
    # member pulled in behind a placement can itself be a metaball.
    metaballs = unpack_metaballs(objects_to_convert)
    _report_promoted_metaball_families(metaballs)

    collection_data = analyze_collection_structure(objects_to_convert)

    if not collection_data["objects"] and not collection_data["collections"]:
        return None

    converted_objects = convert_selected_objects(
        context, objects_to_convert, apply_modifiers, metaballs
    )
    if not converted_objects:
        return None

    # create the root Speckle collection
    root_collection = Collection(name=collection_name)
    root_collection.units = get_scene_units(context.scene).value
    root_collection["version"] = 3

    # maps Blender collection to Speckle collection
    collection_mapping = {}  #

    # create Speckle collections for each blender collection
    for blender_coll in collection_data["collections"]:
        speckle_coll = Collection(name=blender_coll.name)
        speckle_coll.units = root_collection.units
        collection_mapping[blender_coll] = speckle_coll

    for blender_coll in collection_data["collections"]:
        speckle_coll = collection_mapping[blender_coll]

        parent_coll = find_parent_collection(
            blender_coll, collection_data["collections"]
        )

        if parent_coll and parent_coll in collection_mapping:
            parent_speckle_coll = collection_mapping[parent_coll]
            parent_speckle_coll.elements.append(speckle_coll)
        else:
            root_collection.elements.append(speckle_coll)

    # assign objects to their collections
    object_mapping = {}
    for i, blender_obj in enumerate(objects_to_convert):
        if i < len(converted_objects) and converted_objects[i] is not None:
            object_mapping[blender_obj] = as_placement(converted_objects[i], instances)

    for blender_obj, speckle_obj in object_mapping.items():
        placed = False

        target_collection = find_target_collection_for_object(
            blender_obj, collection_data["collections"]
        )

        if target_collection and target_collection in collection_mapping:
            collection_mapping[target_collection].elements.append(speckle_obj)
            placed = True

        # if not placed in any subcollection, add to root
        if not placed:
            root_collection.elements.append(speckle_obj)

    attach_instance_proxies(root_collection, instances)
    attach_metaball_subelements(root_collection, metaballs)
    # Materials are collected here rather than by the caller because only this
    # function sees the expanded object list — a definition member pulled in
    # behind a placement needs its material proxy too.
    add_render_material_proxies_to_base(root_collection, objects_to_convert)

    return root_collection


def as_placement(speckle_obj: Base, instances: InstanceUnpackResult) -> Base:
    """Swap a converted collection-instance empty for its placement proxy.

    Both consumers key on the InstanceProxy *being* the element rather than
    hanging off it: ``to_native`` looks for InstanceProxy instances while
    traversing, and the bundle exporter reads the transform off the element it is
    already walking. The empty's descriptive members ride along on the proxy so
    the placement still reaches the eav table named and queryable.
    """
    proxy = instances.instance_proxies.get(getattr(speckle_obj, "applicationId", None))
    if proxy is None:
        return speckle_obj

    proxy["name"] = speckle_obj.name
    proxy["type"] = getattr(speckle_obj, "type", "EMPTY")
    proxy["properties"] = getattr(speckle_obj, "properties", {})
    return proxy


def attach_instance_proxies(
    root_collection: Collection, instances: InstanceUnpackResult
) -> None:
    """Hang the instancing tables off the root, next to the material proxies."""
    if instances.definition_proxies:
        # the key the C# connectors and to_native both expect
        root_collection["instanceDefinitionProxies"] = instances.definition_proxies

    if instances.definition_only_ids:
        # A Blender-side hint for the bundle exporter, with no equivalent in the
        # C# payload: Rhino can derive "is a definition member" from the
        # definitions alone because a block member is never also a scene object,
        # whereas here it usually is. Only the unpacker knows which members the
        # user selected in their own right, so it says so explicitly.
        root_collection["definitionOnlyObjects"] = sorted(instances.definition_only_ids)


def attach_metaball_subelements(
    root_collection: Collection, metaballs: MetaballUnpackResult
) -> None:
    """Hang the metaball parent/child table off the root.

    A Blender-side hint for the bundle exporter, alongside
    ``definitionOnlyObjects``. The classic send path ignores it and simply
    carries the members as ordinary geometry-less objects, which is what keeps
    ``to_native`` round-tripping without needing to learn about families.
    """
    if metaballs.subelements:
        root_collection["subelementIds"] = metaballs.subelements


def _report_promoted_metaball_families(metaballs: MetaballUnpackResult) -> None:
    """Say so when a family publishes through a member rather than its basis.

    The blob then necessarily includes contributions from siblings the user did
    not select — the isosurface cannot be cut apart — so the geometry is wider
    than the selection. Not silent, but not an error either: the alternative is
    publishing nothing where the viewport clearly shows a shape.
    """
    for family_name in metaballs.promoted_families:
        print(
            f"[speckle] metaball family '{family_name}': basis not selected, "
            "publishing the whole family — the blob includes unselected members"
        )


def analyze_collection_structure(objects: List) -> Dict:
    """
    analyze the collection structure of the given objects
    """
    collections_set = set()
    objects_collections = {}

    direct_collections = set()
    for obj in objects:
        obj_collections = []
        for collection in bpy.data.collections:
            if obj.name in collection.objects:
                direct_collections.add(collection)
                obj_collections.append(collection)
        objects_collections[obj] = obj_collections

    # find all ancestor collections
    def find_all_ancestors(collection):
        """recursively find all ancestor collections"""
        ancestors = set()

        for potential_parent in bpy.data.collections:
            if collection.name in potential_parent.children:
                ancestors.add(potential_parent)
                # Recursively find ancestors of the parent
                ancestors.update(find_all_ancestors(potential_parent))

        return ancestors

    for collection in direct_collections:
        collections_set.add(collection)
        ancestors = find_all_ancestors(collection)
        collections_set.update(ancestors)

    collections_list = list(collections_set)
    collections_list.sort(key=lambda c: get_collection_depth(c))

    return {
        "collections": collections_list,
        "objects": objects,
        "object_collections": objects_collections,
    }


def get_collection_depth(collection: BlenderCollection) -> int:
    """
    get the depth of a collection in the hierarchy
    """
    depth = 0
    for scene in bpy.data.scenes:
        if collection.name in scene.collection.children:
            return depth

    for parent_coll in bpy.data.collections:
        if collection.name in parent_coll.children:
            return get_collection_depth(parent_coll) + 1

    return depth


def find_parent_collection(
    collection: BlenderCollection, all_collections: List[BlenderCollection]
) -> Optional[BlenderCollection]:
    """
    find the parent collection
    """
    for potential_parent in all_collections:
        if collection.name in potential_parent.children:
            return potential_parent
    return None


def find_target_collection_for_object(
    obj, collections: List[BlenderCollection]
) -> Optional[BlenderCollection]:
    """
    find the deepest collection that contains this object
    """
    target_collection = None
    max_depth = -1

    for collection in collections:
        if obj.name in collection.objects:
            depth = get_collection_depth(collection)
            if depth > max_depth:
                max_depth = depth
                target_collection = collection

    return target_collection


def convert_selected_objects(
    context: Context,
    objects_to_convert: List,
    apply_modifiers: bool = True,
    metaballs: Optional[MetaballUnpackResult] = None,
) -> List[Optional[Base]]:
    """
    convert selected objects to Speckle format with proper units
    """
    scene = context.scene
    units = get_scene_units(scene)
    scale_factor = scene.unit_settings.scale_length
    roles = metaballs.roles if metaballs else {}

    speckle_objects = []
    for obj in objects_to_convert:
        if not obj or obj.type not in SUPPORTED_OBJECT_TYPES:
            speckle_objects.append(None)
            continue

        speckle_obj = convert_to_speckle(
            obj,
            scale_factor,
            units.value,
            apply_modifiers,
            metaball_role=roles.get(get_object_id(obj)),
        )
        speckle_objects.append(speckle_obj)

    return speckle_objects


def get_scene_units(scene) -> Units:
    """
    get units from Blender's unit system
    """
    unit_settings = scene.unit_settings

    if unit_settings.system == "METRIC":
        if unit_settings.length_unit == "METERS":
            return Units.m
        elif unit_settings.length_unit == "CENTIMETERS":
            return Units.cm
        elif unit_settings.length_unit == "MILLIMETERS":
            return Units.mm
        elif unit_settings.length_unit == "KILOMETERS":
            return Units.km
        else:
            return Units.m
    elif unit_settings.system == "IMPERIAL":
        if unit_settings.length_unit == "FEET":
            return Units.feet
        elif unit_settings.length_unit == "INCHES":
            return Units.inches
        elif unit_settings.length_unit == "YARDS":
            return Units.yards
        elif unit_settings.length_unit == "MILES":
            return Units.miles
        else:
            return Units.feet
    else:
        return Units.m  # default to meters


def count_objects_in_collection(collection: Collection) -> int:
    """
    recursively count all objects in a collection and its sub-collections
    """
    count = 0
    if hasattr(collection, "elements"):
        for element in collection.elements:
            if isinstance(element, Collection):
                count += count_objects_in_collection(element)
            else:
                count += 1
    return count
