from bpy.types import Object
from specklepy.objects.geometry import Point


def point_to_speckle(blender_object: Object, scale_factor: float = 1.0) -> Point:
    assert blender_object.type == "EMPTY", "Object must be an empty."

    location = blender_object.location

    speckle_point = Point(
        x=location.x * scale_factor,
        y=location.y * scale_factor,
        z=location.z * scale_factor,
        units="",  # TODO: implement units in object level
    )

    return speckle_point
