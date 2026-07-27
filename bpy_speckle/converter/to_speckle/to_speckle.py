from bpy.types import Object
from typing import Optional
from specklepy.objects.data_objects import BlenderObject
from .curve_to_speckle import curve_to_speckle_display_value
from .mesh_to_speckle import mesh_to_speckle_meshes
from .surface_to_speckle import surface_to_speckle_meshes
from .text_to_speckle import text_properties, text_to_speckle_meshes
from .utils import get_object_id, extract_custom_properties


def merge_data_block_properties(object_properties: dict, data_properties: dict) -> dict:
    """Combine object-level and data-block-level custom properties into the
    dict published on the BlenderObject.

    Only this merged dict reaches the parquet bundle's eav table (queryable/
    filterable on the server). Data-block properties are also applied to the
    displayValue geometry, which serializes on classic sends but is dropped
    by the bundle's SGEO geometry encoding.

    TODO: decide how data-block properties surface in the bundle. Options:
    nest them (e.g. ``{**object_properties, "data": data_properties}`` →
    eav paths ``properties.data.<key>``, no collisions, clear provenance);
    merge flat with one side winning on key collisions; or keep the current
    object-only behavior (exact parity with PR #294's reach on classic sends).
    """
    return object_properties


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> Optional[BlenderObject]:
    display_value = []
    properties = merge_data_block_properties(
        extract_custom_properties(blender_object),
        extract_custom_properties(blender_object.data) if blender_object.data else {},
    )

    if blender_object.type == "CURVE":
        # bevelled, extruded and filled curves reach the viewer as tessellated
        # geometry; genuine wire curves keep their NURBS/Bezier definition
        display_value = curve_to_speckle_display_value(
            blender_object, scale_factor, units, apply_modifiers
        )

    elif blender_object.type == "SURFACE":
        # NURBS patches always reach the viewer as tessellated geometry: SGEO
        # has no Surface primitive, so there is no exact route to the bundle
        meshes = surface_to_speckle_meshes(
            blender_object, scale_factor, units, apply_modifiers
        )

        if meshes:
            display_value = meshes

    elif blender_object.type == "MESH":
        # get mesh data - apply modifiers if requested
        mesh_data = blender_object.data
        if apply_modifiers and blender_object.modifiers:
            import bpy

            # use evaluated object to get mesh with modifiers applied
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = blender_object.evaluated_get(depsgraph)
            evaluated_mesh = evaluated_obj.to_mesh()
            mesh_data = evaluated_mesh

        meshes = mesh_to_speckle_meshes(blender_object, mesh_data, scale_factor, units)

        if (
            apply_modifiers
            and blender_object.modifiers
            and mesh_data != blender_object.data
        ):
            blender_object.to_mesh_clear()

        if meshes:
            display_value = meshes

    elif blender_object.type == "FONT":
        # text reaches the viewer as tessellated glyphs; the string and layout
        # settings ride along as properties so they stay queryable
        meshes = text_to_speckle_meshes(
            blender_object, scale_factor, units, apply_modifiers
        )
        properties = {**properties, **text_properties(blender_object.data)}

        if meshes:
            display_value = meshes

    if not display_value:
        return None

    if not isinstance(display_value, list):
        display_value = [display_value]

    return BlenderObject(
        name=blender_object.name,
        type=blender_object.type,
        displayValue=display_value,
        applicationId=get_object_id(blender_object),
        properties=properties,
        units=units,
    )
