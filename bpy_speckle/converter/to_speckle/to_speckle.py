from bpy.types import Object
from typing import Optional
from specklepy.objects.data_objects import BlenderObject
from .curve_to_speckle import curve_to_speckle
from .mesh_to_speckle import mesh_to_speckle


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Optional[BlenderObject]:
    converted_geometry = None
    properties = {}

    if blender_object.type == "CURVE":
        converted_geometry = curve_to_speckle(blender_object, scale_factor)
    elif blender_object.type == "MESH":
        converted_geometry = mesh_to_speckle(
            blender_object, blender_object.data, scale_factor, units
        )

    if not converted_geometry:
        return None

    display_value = []
    if (
        hasattr(converted_geometry, "@displayValue")
        and converted_geometry["@displayValue"]
    ):
        display_value = converted_geometry["@displayValue"]
    elif hasattr(converted_geometry, "@elements") and converted_geometry["@elements"]:
        display_value = converted_geometry["@elements"]
    else:
        display_value = [converted_geometry]

    if not isinstance(display_value, list):
        display_value = [display_value]

    properties["displayValue"] = converted_geometry

    return BlenderObject(
        name=blender_object.name,
        type=blender_object.type,
        displayValue=display_value,
        applicationId=blender_object.name,
        properties=properties,
        units=units,
    )
