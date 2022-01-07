from mathutils import Matrix
from bpy_speckle.convert.to_native import convert_to_native
from bpy_speckle.functions import _report


def set_transform(speckle_object, blender_object):
    transform = None
    if hasattr(speckle_object, "transform"):
        transform = speckle_object.transform
    elif (
        hasattr(speckle_object, "properties") and speckle_object.properties is not None
    ):
        transform = speckle_object.properties.get("transform", None)

    if transform and len(transform) == 16:
        mat = Matrix([transform[:4], transform[4:8], transform[8:12], transform[12:16]])

        blender_object.matrix_world = mat


def try_add_property(speckle_object, blender_object, prop, prop_name):
    if prop in speckle_object.keys() and speckle_object[prop] is not None:
        blender_object[prop_name] = speckle_object[prop]


def get_speckle_subobjects(attr, scale, name):
    subobjects = []
    for key in attr.keys():
        if isinstance(attr[key], dict):
            subtype = attr[key].get("type", None)
            if subtype:
                name = f"{name}.{key}"
                subobject = convert_to_native(attr[key], name)

                subobjects.append(subobject)
                props = attr[key].get("properties", None)
                if props:
                    subobjects.extend(get_speckle_subobjects(props, scale, name))
        elif hasattr(attr[key], "type"):
            subtype = attr[key].type
            if subtype:
                name = "{}.{}".format(name, key)
                subobject = convert_to_native(attr[key], name)

                subobjects.append(subobject)
                props = attr[key].get("properties", None)
                if props:
                    subobjects.extend(get_speckle_subobjects(props, scale, name))
    return subobjects
