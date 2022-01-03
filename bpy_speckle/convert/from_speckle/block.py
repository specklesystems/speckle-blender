import bpy
from mathutils import Matrix
from bpy_speckle.functions import _report
from specklepy.objects.geometry import *
from specklepy.objects.other import BlockInstance, BlockDefinition, Transform
from .. import from_speckle_object


def transform_to_native(transform: Transform, scale=1.0):
    mat = Matrix(
        [
            transform.value[:4],
            transform.value[4:8],
            transform.value[8:12],
            transform.value[12:16],
        ]
    )
    # scale the translation
    for i in range(3):
        mat[i][3] *= scale
    return mat


def block_def_to_native(definition: BlockDefinition, scale=1.0):
    _report(f">>> creating block definition for {definition.name} ({definition.id})")
    native_def = bpy.data.collections.get(definition.name)
    if native_def:
        return native_def

    native_def = bpy.data.collections.new(definition.name)
    for geo in definition.geometry:
        b_obj = from_speckle_object(geo, scale)
        native_def.objects.link(b_obj)

    return native_def


def import_block(instance: BlockInstance, scale=1.0, name=None):
    """
    Convert BlockInstance to native
    """
    _report(f">>> converting block instance {instance.id}")

    name = getattr(instance, "name", "") or f"BlockInstance -- {instance.id}"
    native_def = block_def_to_native(instance.blockDefinition, scale)

    native_instance = bpy.data.objects.new(name, None)
    native_instance.instance_collection = native_def
    native_instance.instance_type = "COLLECTION"
    native_instance.matrix_world = transform_to_native(instance.transform, scale)

    return native_instance