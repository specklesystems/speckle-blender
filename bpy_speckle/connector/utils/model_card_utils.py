from typing import Any, Dict, Optional

import bpy
from bpy.types import Context

from ..utils.property_groups import speckle_model_card


def find_layer_collection(layer_collection, collection_name):
    """
    Recursively find a layer collection by collection name
    """
    if layer_collection.collection.name == collection_name:
        return layer_collection
    for child in layer_collection.children:
        result = find_layer_collection(child, collection_name)
        if result:
            return result
    return None


def get_object_by_application_id(app_id: str):
    """
    Find a Blender object by its applicationId stored in custom property
    """
    if not app_id:
        return None

    for obj in bpy.data.objects:
        if "applicationId" in obj and obj["applicationId"] == app_id:
            return obj
    return None


def get_objects_by_application_ids(app_ids: list):
    """
    Find multiple Blender objects by their applicationIds
    """
    if not app_ids:
        return {}

    result = {}
    for obj in bpy.data.objects:
        if "applicationId" in obj and obj["applicationId"] in app_ids:
            result[obj["applicationId"]] = obj
    return result


def get_collection_by_application_id(app_id: str):
    """
    Find a Blender collection by its applicationId stored in custom property
    """
    if not app_id:
        return None

    for collection in bpy.data.collections:
        if "applicationId" in collection and collection["applicationId"] == app_id:
            return collection
    return None


def get_collection_identifier(blender_col: bpy.types.Collection) -> str:
    """
    Get collection identifier: applicationId if exists, fallback to name
    """
    if "applicationId" in blender_col and blender_col["applicationId"]:
        return blender_col["applicationId"]
    return blender_col.name


def find_collection_by_identifier(identifier: str):
    """
    Find collection by identifier: try applicationId first, then name
    """
    # first try to find by applicationId
    collection = get_collection_by_application_id(identifier)
    if collection:
        return collection

    # fallback to name-based lookup
    return bpy.data.collections.get(identifier)


def capture_modifier_data(blender_obj: bpy.types.Object) -> list:
    """
    Capture modifier data from a Blender object as dictionaries
    """
    modifiers_data = []
    for modifier in blender_obj.modifiers:
        modifier_data = {
            "name": modifier.name,
            "type": modifier.type,
            "show_viewport": modifier.show_viewport,
            "show_render": modifier.show_render,
            "show_in_editmode": modifier.show_in_editmode,
            "show_on_cage": modifier.show_on_cage,
            "properties": {},
        }

        # Capture modifier-specific properties
        for prop_name in modifier.bl_rna.properties.keys():
            if prop_name in [
                "rna_type",
                "name",
                "type",
                "show_viewport",
                "show_render",
                "show_in_editmode",
                "show_on_cage",
            ]:
                continue
            try:
                if hasattr(modifier, prop_name):
                    prop_value = getattr(modifier, prop_name)
                    # Handle different property types
                    if isinstance(prop_value, (int, float, bool, str)):
                        modifier_data["properties"][prop_name] = prop_value
                    elif hasattr(prop_value, "name"):  # Object references
                        modifier_data["properties"][prop_name] = prop_value.name
                    elif (
                        hasattr(prop_value, "__len__") and len(prop_value) <= 4
                    ):  # Vectors/colors
                        modifier_data["properties"][prop_name] = list(prop_value)
            except (AttributeError, TypeError):
                continue

        modifiers_data.append(modifier_data)

    return modifiers_data


def has_visibility_modifications(obj: bpy.types.Object) -> bool:
    """Check if object has non-default visibility settings"""
    return obj.hide_viewport or obj.hide_select or obj.hide_render or obj.hide_get()


def has_modifier_modifications(obj: bpy.types.Object) -> bool:
    """Check if object has any modifiers applied"""
    return hasattr(obj, "modifiers") and len(obj.modifiers) > 0


def has_collection_visibility_modifications(layer_col, collection) -> bool:
    """Check if collection has non-default visibility settings"""
    return (
        layer_col.hide_viewport
        or collection.hide_select
        or collection.hide_render
        or layer_col.exclude
    )


def collect_objects_with_properties(
    model_card: speckle_model_card,
) -> Dict[str, Dict[str, Any]]:
    """
    Collect objects and collections with their current properties before deletion
    Only stores data for objects that have been modified from defaults
    """
    collected_data = {"objects": {}, "collections": {}}

    # Collect object properties (only for modified objects)
    for s_obj in model_card.objects:
        blender_obj = get_object_by_application_id(s_obj.applicationId)
        if blender_obj:
            obj_data = {}

            # Only collect visibility if modified from defaults
            if has_visibility_modifications(blender_obj):
                obj_data["visibility"] = {
                    "hide_get": blender_obj.hide_get(),
                    "hide_viewport": blender_obj.hide_viewport,
                    "hide_select": blender_obj.hide_select,
                    "hide_render": blender_obj.hide_render,
                }

            # Only collect modifiers if object has any
            if has_modifier_modifications(blender_obj):
                obj_data["modifiers"] = capture_modifier_data(blender_obj)

            # Only store object data if it has modifications
            if obj_data:
                collected_data["objects"][s_obj.applicationId] = obj_data

    # Collect collection properties (only for modified collections)
    for s_col in model_card.collections:
        # try to find collection by applicationId first, then fallback to name
        blender_col = None
        if s_col.applicationId:
            blender_col = get_collection_by_application_id(s_col.applicationId)
        if not blender_col:
            blender_col = bpy.data.collections.get(s_col.name)

        if blender_col:
            view_layer = bpy.context.view_layer
            if view_layer:
                layer_col = find_layer_collection(
                    view_layer.layer_collection, blender_col.name
                )
                if layer_col and has_collection_visibility_modifications(
                    layer_col, blender_col
                ):
                    # use collection identifier as key
                    collection_id = get_collection_identifier(blender_col)
                    collected_data["collections"][collection_id] = {
                        "hide_viewport": layer_col.hide_viewport,
                        "hide_select": layer_col.collection.hide_select,
                        "hide_render": layer_col.collection.hide_render,
                        "exclude_from_view_layer": layer_col.exclude,
                    }

    return collected_data


def transfer_object_properties(
    new_obj: bpy.types.Object, old_obj_data: Dict[str, Any]
) -> None:
    """
    Transfer visibility and modifiers from old object data to new object
    Handles sparse data gracefully - applies defaults when data is missing
    """
    # Transfer visibility settings (if any were modified)
    visibility = old_obj_data.get("visibility")
    if visibility:
        new_obj.hide_set(visibility.get("hide_get", False))
        new_obj.hide_viewport = visibility.get("hide_viewport", False)
        new_obj.hide_select = visibility.get("hide_select", False)
        new_obj.hide_render = visibility.get("hide_render", False)
    # If no visibility data, object keeps defaults (all False)

    # Transfer modifiers (if any were present)
    old_modifiers = old_obj_data.get("modifiers")
    if old_modifiers and hasattr(new_obj, "modifiers"):
        # Clear existing modifiers
        new_obj.modifiers.clear()

        # Transfer each modifier
        for modifier_data in old_modifiers:
            recreate_modifier_from_data(new_obj, modifier_data)
    # If no modifier data, object keeps default (no modifiers)


def transfer_collection_properties(
    new_col: bpy.types.Collection, old_col_data: Dict[str, Any]
) -> None:
    """
    Transfer visibility properties from old collection data to new collection
    Handles sparse data gracefully - applies defaults when data is missing
    """
    view_layer = bpy.context.view_layer
    if view_layer:
        layer_col = find_layer_collection(view_layer.layer_collection, new_col.name)
        if layer_col:
            # Only apply properties if collection had modifications
            # (otherwise it keeps defaults: all False)
            layer_col.hide_viewport = old_col_data.get("hide_viewport", False)
            layer_col.collection.hide_select = old_col_data.get("hide_select", False)
            layer_col.collection.hide_render = old_col_data.get("hide_render", False)
            layer_col.exclude = old_col_data.get("exclude_from_view_layer", False)


def recreate_modifier_from_data(
    new_obj: bpy.types.Object, modifier_data: Dict[str, Any]
) -> Optional[bpy.types.Modifier]:
    """
    Recreate a modifier from captured data
    """
    try:
        # Validate modifier data
        if not modifier_data.get("type") or not modifier_data.get("name"):
            print(f"Invalid modifier data: {modifier_data}")
            return None

        # Create new modifier
        new_modifier = new_obj.modifiers.new(
            modifier_data["name"], modifier_data["type"]
        )

        # Set visibility properties
        new_modifier.show_viewport = modifier_data.get("show_viewport", True)
        new_modifier.show_render = modifier_data.get("show_render", True)
        new_modifier.show_in_editmode = modifier_data.get("show_in_editmode", True)
        new_modifier.show_on_cage = modifier_data.get("show_on_cage", False)

        # Set modifier-specific properties
        for prop_name, prop_value in modifier_data.get("properties", {}).items():
            try:
                if hasattr(new_modifier, prop_name):
                    current_value = getattr(new_modifier, prop_name)
                    # Handle object references
                    if hasattr(current_value, "name") and isinstance(prop_value, str):
                        referenced_obj = bpy.data.objects.get(prop_value)
                        if referenced_obj:
                            setattr(new_modifier, prop_name, referenced_obj)
                    else:
                        setattr(new_modifier, prop_name, prop_value)
            except (AttributeError, TypeError):
                continue

        return new_modifier
    except Exception as e:
        print(f"Error recreating modifier {modifier_data.get('name', 'unknown')}: {e}")
        return None


def update_model_card_objects(
    model_card: speckle_model_card,
    converted_objects: Dict[str, bpy.types.Object | bpy.types.Collection],
    old_properties: Optional[Dict[str, Dict[str, Any]]] = None,
):
    """
    Update model card with new objects and apply properties from old objects if provided
    """
    # Clear model card objects
    model_card.objects.clear()
    model_card.collections.clear()

    # Convert list to dictionary if needed
    if isinstance(converted_objects, list):
        converted_objects = {obj.name: obj for obj in converted_objects}

    # Using a set keeps lookup O(1)
    object_names = set()
    collection_names = set()

    for obj in converted_objects.values():
        # Handle collections
        if isinstance(obj, bpy.types.Collection):
            if obj.name in collection_names:
                continue
            collection_names.add(obj.name)

            s_col = model_card.collections.add()
            s_col.name = obj.name
            # .get's default only applies when the key is absent — a present
            # custom property can still hold None, which StringProperty rejects
            s_col.applicationId = str(obj.get("applicationId") or "")

            # apply old collection properties if available (use identifier-based lookup)
            if old_properties:
                collection_id = get_collection_identifier(obj)
                if collection_id in old_properties.get("collections", {}):
                    old_col_data = old_properties["collections"][collection_id]
                    transfer_collection_properties(obj, old_col_data)

        # Handle objects
        elif isinstance(obj, bpy.types.Object):
            if obj.name in object_names:
                continue
            object_names.add(obj.name)

            s_obj = model_card.objects.add()
            s_obj.name = obj.name
            s_obj.applicationId = str(obj.get("applicationId") or "")

            # Apply old object properties if available
            if (
                old_properties
                and s_obj.applicationId
                and s_obj.applicationId in old_properties.get("objects", {})
            ):
                old_obj_data = old_properties["objects"][s_obj.applicationId]
                transfer_object_properties(obj, old_obj_data)


def format_load_summary(model_card: speckle_model_card) -> str:
    """
    Build the status-bar summary for a finished load.

    Counts the model card's own lists rather than the converted_objects dict:
    that dict keys objects under both their id and their applicationId, so its
    length overstates what actually arrived. Zero is a legitimate result for a
    version with no objects.
    """
    return (
        f"{len(model_card.objects)} objects loaded from Speckle. "
        f"Model: {model_card.model_name}, Version: {model_card.version_id}"
    )


def delete_model_card_objects(model_card: speckle_model_card, context: Context) -> None:
    """
    deletes the model card objects
    """
    # Delete objects directly without requiring selection
    for obj in model_card.objects:
        blender_obj = get_object_by_application_id(obj.applicationId)
        if not blender_obj:
            continue

        # Remove object from all collections first
        for collection in blender_obj.users_collection:
            collection.objects.unlink(blender_obj)

        # Delete the object directly
        bpy.data.objects.remove(blender_obj)

    # delete model card/currently loaded collections
    for col in model_card.collections:
        coll = bpy.data.collections.get(col.name)
        if not coll:
            continue
        # unlink from scenes
        for scene in bpy.data.scenes:
            if scene.collection.children.get(coll.name):
                scene.collection.children.unlink(coll)
        bpy.data.collections.remove(coll)


def select_model_card_objects(model_card, context: Context):
    # deselect all objects first
    bpy.ops.object.select_all(action="DESELECT")
    # select objects in model card
    for obj in model_card.objects:
        blender_obj = get_object_by_application_id(obj.applicationId)
        if not blender_obj:
            continue
        if blender_obj.name in context.view_layer.objects:
            blender_obj.select_set(True)

    selected = context.selected_objects
    if selected:
        context.view_layer.objects.active = selected[0]


def zoom_to_selected_objects(context: Context):
    """
    zooms to the selected objects
    """
    bpy.ops.view3d.view_selected()


def model_card_exists(
    project_id: str, model_id: str, is_publish: bool, context: Context
) -> bool:
    """
    checks if a model card exists
    """
    for model_card in context.scene.speckle_state.model_cards:
        if (
            model_card.project_id == project_id
            and model_card.model_id == model_id
            and model_card.is_publish == is_publish
        ):
            return True
    return False
