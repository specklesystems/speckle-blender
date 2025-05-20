from bpy.types import Object
from typing import Optional
from specklepy.objects.base import Base
from .curve_to_speckle import curve_to_speckle


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
) -> Optional[Base]:
    pass

    speckle_object = None

    if blender_object.type == "CURVE":
        speckle_object = curve_to_speckle(blender_object, scale_factor)

    # apply common properties
    if speckle_object:
        speckle_object.units = units
        speckle_object.name = blender_object.name
        speckle_object.applicationId = blender_object.name

    return speckle_object
