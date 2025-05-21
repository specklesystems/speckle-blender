from bpy.types import Object
from typing import Optional
from specklepy.objects.base import Base
from .curve_to_speckle import curve_to_speckle
from .mesh_to_speckle import mesh_to_speckle


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Optional[Base]:
    """
    Convert a Blender object to a Speckle object.
    
    Args:
        blender_object: The Blender object to convert
        scale_factor: Scale factor to convert to desired units
        units: The desired units (e.g. 'm', 'ft')
        
    Returns:
        A Speckle Base object, or None if conversion failed
    """
    speckle_object = None

    if blender_object.type == "CURVE":
        speckle_object = curve_to_speckle(blender_object, scale_factor)
    elif blender_object.type == "MESH":
        speckle_object = mesh_to_speckle(blender_object, blender_object.data, scale_factor, units)

    # apply common properties
    if speckle_object:
        speckle_object.units = units
        speckle_object.name = blender_object.name
        speckle_object.applicationId = blender_object.name

    return speckle_object
