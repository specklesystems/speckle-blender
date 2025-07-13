import bpy
import json
from bpy.types import Context
from typing import Dict
import json
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


def store_visibility_settings(model_card: speckle_model_card):
    """
    Store current visibility settings of model card objects and collections
    This is used to restore the visibility settings of the loaded objects after loading a new version
    """
    for s_obj in model_card.objects:
        blender_obj = get_object_by_application_id(s_obj.applicationId)
        if blender_obj:
            s_obj.hide_get = blender_obj.hide_get()
            s_obj.hide_viewport = blender_obj.hide_viewport
            s_obj.hide_select = blender_obj.hide_select
            s_obj.hide_render = blender_obj.hide_render

    for s_col in model_card.collections:
        blender_col = bpy.data.collections.get(s_col.name)
        if blender_col:
            # For collections, visibility is controlled through the view layer system
            view_layer = bpy.context.view_layer
            if view_layer:
                # Find the layer collection for this collection
                layer_col = find_layer_collection(
                    view_layer.layer_collection, blender_col.name
                )
                if layer_col:
                    s_col.hide_viewport = layer_col.hide_viewport
                    s_col.hide_select = layer_col.collection.hide_select
                    s_col.hide_render = layer_col.collection.hide_render
                    s_col.exclude_from_view_layer = layer_col.exclude
                else:
                    s_col.hide_viewport = False
                    s_col.hide_select = False
                    s_col.hide_render = False
                    s_col.exclude_from_view_layer = False


def store_uv_mappings(model_card: speckle_model_card):
    """
    Store current UV mapping data of model card mesh objects
    This is used to restore the UV mappings after loading a new version
    """
    for s_obj in model_card.objects:
        blender_obj = bpy.data.objects.get(s_obj.name)

        if blender_obj and blender_obj.type == "MESH" and blender_obj.data:
            mesh = blender_obj.data

            uv_data = {"active_uv_layer": "", "uv_layers": []}

            # Store active UV layer name
            if mesh.uv_layers.active:
                uv_data["active_uv_layer"] = mesh.uv_layers.active.name

            # Store UV data for each UV layer
            for uv_layer in mesh.uv_layers:
                # Extract UV coordinates for all loops in this layer
                uv_coords = []
                for uv_loop in uv_layer.data:
                    uv_coords.extend([uv_loop.uv.x, uv_loop.uv.y])

                uv_data["uv_layers"].append(
                    {"name": uv_layer.name, "uv_coords": uv_coords}
                )

            # Serialize complete UV data as JSON string
            s_obj.uv_data_serialized = json.dumps(uv_data)


def restore_uv_mappings(
    model_card: speckle_model_card,
    converted_objects: Dict[str, bpy.types.Object | bpy.types.Collection],
):
    """
    Restore UV mapping data to reloaded mesh objects
    """
    # First, collect UV mapping data from property groups before they are cleared
    uv_mapping_data = {}
    for s_obj in model_card.objects:
        if s_obj.uv_data_serialized:  # Only process objects that have UV data stored
            try:
                uv_data = json.loads(s_obj.uv_data_serialized)
                uv_mapping_data[s_obj.name] = uv_data
            except (json.JSONDecodeError, ValueError):
                # Skip invalid UV data
                continue

    # Now restore UV mappings to the new objects
    for obj_name, uv_data in uv_mapping_data.items():
        if obj_name in converted_objects:
            blender_obj = converted_objects[obj_name]

            # Only process mesh objects
            if (
                isinstance(blender_obj, bpy.types.Object)
                and blender_obj.type == "MESH"
                and blender_obj.data
            ):
                mesh = blender_obj.data

                # Restore UV layers
                for uv_layer_data in uv_data.get("uv_layers", []):
                    layer_name = uv_layer_data["name"]
                    uv_coords = uv_layer_data["uv_coords"]

                    # Find or create the UV layer
                    uv_layer = mesh.uv_layers.get(layer_name)
                    if not uv_layer:
                        uv_layer = mesh.uv_layers.new(name=layer_name)

                    # Restore UV coordinates
                    expected_coords = len(mesh.loops) * 2  # 2 coords per loop

                    if len(uv_coords) == expected_coords:
                        for i, uv_loop in enumerate(uv_layer.data):
                            coord_idx = i * 2
                            if coord_idx + 1 < len(uv_coords):
                                uv_loop.uv = (
                                    uv_coords[coord_idx],
                                    uv_coords[coord_idx + 1],
                                )

                # Restore active UV layer
                active_uv_layer = uv_data.get("active_uv_layer", "")
                if active_uv_layer and mesh.uv_layers.get(active_uv_layer):
                    mesh.uv_layers.active = mesh.uv_layers[active_uv_layer]


def update_model_card_objects(
    model_card: speckle_model_card,
    converted_objects: Dict[str, bpy.types.Object | bpy.types.Collection],
):
    # Restore UV mappings before clearing property groups
    restore_uv_mappings(model_card, converted_objects)

    # Store visibility settings from property group before clearing
    visibility_settings = {}
    for s_obj in model_card.objects:
        if s_obj.applicationId:
            visibility_settings[s_obj.applicationId] = {
                "hide_get": s_obj.hide_get,
                "hide_viewport": s_obj.hide_viewport,
                "hide_select": s_obj.hide_select,
                "hide_render": s_obj.hide_render,
            }

    # Store modifier settings from property group before clearing
    modifier_settings = {}
    for s_obj in model_card.objects:
        if s_obj.applicationId:
            modifier_settings[s_obj.applicationId] = s_obj.modifiers

    # Store collection visibility settings from property group before clearing
    collection_visibility_settings = {}
    for s_col in model_card.collections:
        collection_visibility_settings[s_col.name] = {
            "hide_viewport": s_col.hide_viewport,
            "hide_select": s_col.hide_select,
            "hide_render": s_col.hide_render,
            "exclude_from_view_layer": s_col.exclude_from_view_layer,
        }

    # clear model card objects
    model_card.objects.clear()
    model_card.collections.clear()

    # if converted_objects is a list, convert it to a dictionary
    if isinstance(converted_objects, list):
        converted_objects = {obj.name: obj for obj in converted_objects}

    for obj in converted_objects.values():
        # if its a collection, add it to collections field of model card
        if isinstance(obj, bpy.types.Collection):
            if obj.name in (o.name for o in model_card.collections):
                continue
            s_col = model_card.collections.add()
            s_col.name = obj.name

            # Restore collection visibility settings if they exist
            if obj.name in collection_visibility_settings:
                s_col.hide_viewport = collection_visibility_settings[obj.name][
                    "hide_viewport"
                ]
                s_col.hide_select = collection_visibility_settings[obj.name][
                    "hide_select"
                ]
                s_col.hide_render = collection_visibility_settings[obj.name][
                    "hide_render"
                ]
                s_col.exclude_from_view_layer = collection_visibility_settings[
                    obj.name
                ]["exclude_from_view_layer"]

                # Apply the visibility settings to the new collection through view layer
                view_layer = bpy.context.view_layer
                if view_layer:
                    # Find the layer collection for this collection
                    layer_col = find_layer_collection(
                        view_layer.layer_collection, obj.name
                    )
                    if layer_col:
                        # Apply viewport visibility (controlled by layer collection)
                        layer_col.hide_viewport = collection_visibility_settings[
                            obj.name
                        ]["hide_viewport"]
                        # Apply selectability and render visibility (controlled by collection)
                        obj.hide_select = collection_visibility_settings[obj.name][
                            "hide_select"
                        ]
                        obj.hide_render = collection_visibility_settings[obj.name][
                            "hide_render"
                        ]
                        # Apply view layer exclusion
                        layer_col.exclude = collection_visibility_settings[obj.name][
                            "exclude_from_view_layer"
                        ]

        # if its an object, add it to the objects field of model card
        if isinstance(obj, bpy.types.Object):
            if obj.name in (o.name for o in model_card.objects):
                continue
            s_obj = model_card.objects.add()
            s_obj.name = obj.name
            s_obj.applicationId = obj.get("applicationId", "")
            # Restore visibility settings if they exist
            if s_obj.applicationId and s_obj.applicationId in visibility_settings:
                s_obj.hide_get = visibility_settings[s_obj.applicationId]["hide_get"]
                s_obj.hide_viewport = visibility_settings[s_obj.applicationId][
                    "hide_viewport"
                ]
                s_obj.hide_select = visibility_settings[s_obj.applicationId][
                    "hide_select"
                ]
                s_obj.hide_render = visibility_settings[s_obj.applicationId][
                    "hide_render"
                ]

                # Apply the visibility settings to the new object
                obj.hide_set(visibility_settings[s_obj.applicationId]["hide_get"])
                obj.hide_viewport = visibility_settings[s_obj.applicationId][
                    "hide_viewport"
                ]
                obj.hide_select = visibility_settings[s_obj.applicationId][
                    "hide_select"
                ]
                obj.hide_render = visibility_settings[s_obj.applicationId][
                    "hide_render"
                ]

            # Restore modifier settings if they exist
            if s_obj.applicationId and s_obj.applicationId in modifier_settings:
                s_obj.modifiers = modifier_settings[s_obj.applicationId]
                restore_modifier_settings(obj, modifier_settings[s_obj.applicationId])


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


def serialize_modifier(modifier):
    """
    Serialize a Blender modifier to a dictionary
    """
    modifier_data = {
        "name": modifier.name,
        "type": modifier.type,
        "show_viewport": modifier.show_viewport,
        "show_render": modifier.show_render,
        "show_in_editmode": modifier.show_in_editmode,
        "show_on_cage": modifier.show_on_cage,
        "properties": {},
    }

    # Store all modifier-specific properties
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
            # Skip properties that can't be serialized
            continue

    return modifier_data


def deserialize_modifier(obj, modifier_data):
    """
    Recreate a modifier from serialized data
    """
    try:
        modifier = obj.modifiers.new(modifier_data["name"], modifier_data["type"])

        # Set visibility properties
        modifier.show_viewport = modifier_data.get("show_viewport", True)
        modifier.show_render = modifier_data.get("show_render", True)
        modifier.show_in_editmode = modifier_data.get("show_in_editmode", True)
        modifier.show_on_cage = modifier_data.get("show_on_cage", False)

        # Set modifier-specific properties
        for prop_name, prop_value in modifier_data.get("properties", {}).items():
            try:
                if hasattr(modifier, prop_name):
                    current_value = getattr(modifier, prop_name)
                    # Handle object references
                    if hasattr(current_value, "name") and isinstance(prop_value, str):
                        referenced_obj = bpy.data.objects.get(prop_value)
                        if referenced_obj:
                            setattr(modifier, prop_name, referenced_obj)
                    else:
                        setattr(modifier, prop_name, prop_value)
            except (AttributeError, TypeError):
                # Skip properties that can't be set
                continue

        return modifier
    except Exception as e:
        print(f"Error deserializing modifier {modifier_data['name']}: {e}")
        return None


def store_modifier_settings(model_card: speckle_model_card):
    """
    Store current modifier settings of model card objects
    This is used to restore the modifier settings of the loaded objects after loading a new version
    """
    for s_obj in model_card.objects:
        blender_obj = get_object_by_application_id(s_obj.applicationId)
        if blender_obj and hasattr(blender_obj, "modifiers"):
            modifiers_data = []
            for modifier in blender_obj.modifiers:
                modifier_data = serialize_modifier(modifier)
                modifiers_data.append(modifier_data)

            # Store as JSON string
            s_obj.modifiers = json.dumps(modifiers_data)


def restore_modifier_settings(blender_obj, modifier_data_json):
    """
    Restore modifier settings to a Blender object
    """
    if not modifier_data_json or not hasattr(blender_obj, "modifiers"):
        return

    try:
        modifiers_data = json.loads(modifier_data_json)

        # Clear existing modifiers
        blender_obj.modifiers.clear()

        # Recreate modifiers
        for modifier_data in modifiers_data:
            deserialize_modifier(blender_obj, modifier_data)

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error restoring modifiers for {blender_obj.name}: {e}")
