import bpy

OBJECT_NAME_SPECKLE_SEPARATOR = " -- "
SPECKLE_ID_LENGTH = 32
_QUICK_TEST_NAME_LENGTH = SPECKLE_ID_LENGTH + len(OBJECT_NAME_SPECKLE_SEPARATOR)


def to_speckle_name(blender_object: bpy.types.ID) -> str:
    does_name_contain_id = (
        len(blender_object.name) > _QUICK_TEST_NAME_LENGTH
        and OBJECT_NAME_SPECKLE_SEPARATOR in blender_object.name
    )
    if does_name_contain_id:
        return blender_object.name.rsplit(OBJECT_NAME_SPECKLE_SEPARATOR, 1)[0]
    else:
        return blender_object.name
