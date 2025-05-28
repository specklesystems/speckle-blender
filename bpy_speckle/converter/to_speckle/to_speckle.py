from bpy.types import Object
from typing import Optional
from specklepy.objects.data_objects import BlenderObject
from .curve_to_speckle import curve_to_speckle
from .mesh_to_speckle import mesh_to_speckle_meshes


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Optional[BlenderObject]:
    display_value = []
    properties = {}

    if blender_object.type == "CURVE":
        curve_result = curve_to_speckle(blender_object, scale_factor)
        if curve_result and hasattr(curve_result, "@elements"):
            display_value = curve_result["@elements"]
        elif curve_result:
            display_value = [curve_result]

    elif blender_object.type == "MESH":
        meshes = mesh_to_speckle_meshes(
            blender_object, blender_object.data, scale_factor, units
        )
        if meshes:
            for mesh in meshes:
                if hasattr(mesh, "applicationId"):
                    mesh.applicationId = None
            display_value = meshes

    if not display_value:
        return None

    if not isinstance(display_value, list):
        display_value = [display_value]

    return BlenderObject(
        name=blender_object.name,
        type=blender_object.type,
        displayValue=display_value,
        applicationId=blender_object.name,
        properties=properties,
        units=units,
    )
