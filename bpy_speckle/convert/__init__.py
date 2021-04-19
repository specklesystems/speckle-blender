import bpy, idprop
from mathutils import Matrix

from .from_speckle import *
from .to_speckle import *
from bpy_speckle.util import find_key_case_insensitive
from bpy_speckle.functions import _report

from specklepy.objects.geometry import *

FROM_SPECKLE_SCHEMAS = {
    Mesh: import_mesh,
    Brep: import_brep,
    Curve: import_curve,
    Line: import_curve,
    Polyline: import_curve,
    Polycurve: import_curve,
    Arc: import_curve,
}


# FROM_SPECKLE = {
#     "Mesh": import_mesh,
#     "Brep": import_brep,
#     "Curve": import_curve,
#     "Line": import_curve,
#     "Polyline": import_curve,
#     "Polycurve":import_curve,
#     "Arc":import_curve,
# }


TO_SPECKLE = {
    "MESH": export_mesh,
    "CURVE": export_curve,
    "EMPTY": export_empty,
}


def set_transform(speckle_object, blender_object):
    transform = None
    if hasattr(speckle_object, "transform"):
        transform = speckle_object.transform
    elif (
        hasattr(speckle_object, "properties") and speckle_object.properties is not None
    ):
        transform = speckle_object.properties.get("transform", None)

    if transform:
        if len(transform) == 16:
            mat = Matrix(
                [transform[0:4], transform[4:8], transform[8:12], transform[12:16]]
            )
            blender_object.matrix_world = mat


def add_material(smesh, blender_object):
    if blender_object.data == None:
        return
        # Add material if there is one
    if not hasattr(smesh, "properties"):
        return

    props = smesh.properties
    if props:
        material = find_key_case_insensitive(props, "material")
        if material:
            material_name = material.get("name", None)
            if material_name:
                mat = bpy.data.materials.get(material_name)

                if mat is None:
                    mat = bpy.data.materials.new(name=material_name)
                blender_object.data.materials.append(mat)
                del material


def try_add_property(speckle_object, blender_object, prop, prop_name):
    if prop in speckle_object.keys() and speckle_object[prop] is not None:
        blender_object[prop_name] = speckle_object[prop]


# def add_dictionary(prop, blender_object, superkey=None):
#     for key in prop.keys():
#         key_name = "{}.{}".format(superkey, key) if superkey else "{}".format(key)
#         if isinstance(prop[key], dict):
#             subtype = prop[key].get("type", None)
#             if subtype and subtype in FROM_SPECKLE.keys():
#                 continue
#             else:
#                 add_dictionary(prop[key], blender_object, key_name)
#         elif hasattr(prop[key], "type"):
#             subtype = prop[key].type
#             if subtype and subtype in FROM_SPECKLE.keys():
#                 continue
#         else:
#             try:
#                 blender_object[key_name] = prop[key]
#             except KeyError:
#                 pass


def add_custom_properties(speckle_object, blender_object):

    if blender_object is None:
        return

    blender_object["_speckle_type"] = type(speckle_object).__name__
    # blender_object['_speckle_name'] = "SpeckleObject"

    properties = None

    ignore = ["_chunkable", "_units"]

    for key in speckle_object.get_dynamic_member_names():
        if key in ignore:
            continue
        if (
            isinstance(speckle_object[key], int)
            or isinstance(speckle_object[key], str)
            or isinstance(speckle_object[key], float)
            or isinstance(speckle_object[key], dict)
        ):
            blender_object[key] = speckle_object[key]

    # if properties:
    #     add_dictionary(properties, blender_object, "")


def dict_to_speckle_object(data):
    if "type" in data.keys() and data["type"] in SCHEMAS.keys():
        obj = SCHEMAS[data["type"]].parse_obj(data)
        for key in obj.properties.keys():
            if isinstance(obj.properties[key], dict):
                obj.properties[key] = dict_to_speckle_object(obj.properties[key])
            elif isinstance(obj.properties[key], list):
                for i in range(len(obj.properties[key])):
                    if isinstance(obj.properties[key][i], dict):
                        obj.properties[key][i] = dict_to_speckle_object(
                            obj.properties[key][i]
                        )
        return obj
    else:
        for key in data.keys():
            if isinstance(data[key], dict):
                data[key] = dict_to_speckle_object(data[key])
            elif isinstance(data[key], list):
                for i in range(len(data[key])):
                    if isinstance(data[key][i], dict):
                        data[key][i] = dict_to_speckle_object(data[key][i])
        return data


def from_speckle_object(speckle_object, scale, name=None):
    if type(speckle_object) in FROM_SPECKLE_SCHEMAS.keys():
        # print("Got object type: {}".format(type(speckle_object)))
        if name:
            speckle_name = name
        elif hasattr(speckle_object, "name") and speckle_object.name:
            speckle_name = speckle_object.name
        elif speckle_object.id:
            speckle_name = speckle_object.id
        else:
            speckle_name = "Unidentified Speckle Object"

        obdata = FROM_SPECKLE_SCHEMAS[type(speckle_object)](
            speckle_object, scale, speckle_name
        )

        if speckle_name in bpy.data.objects.keys():
            blender_object = bpy.data.objects[speckle_name]
            blender_object.data = obdata
            if hasattr(obdata, "materials"):
                blender_object.data.materials.clear()
        else:
            blender_object = bpy.data.objects.new(speckle_name, obdata)

        blender_object.speckle.object_id = str(speckle_object.id)
        blender_object.speckle.enabled = True

        add_custom_properties(speckle_object, blender_object)
        add_material(speckle_object, blender_object)
        set_transform(speckle_object, blender_object)

        return blender_object

    else:
        _report("Invalid input: {}".format(speckle_object))
        return None


def get_speckle_subobjects(attr, scale, name):

    subobjects = []
    for key in attr.keys():
        if isinstance(attr[key], dict):
            subtype = attr[key].get("type", None)
            if subtype:
                name = "{}.{}".format(name, key)
                # print("{} :: {}".format(name, subtype))
                subobject = from_speckle_object(attr[key], scale, name)
                add_custom_properties(attr[key], subobject)

                subobjects.append(subobject)
                props = attr[key].get("properties", None)
                if props:
                    subobjects.extend(get_speckle_subobjects(props, scale, name))
        elif hasattr(attr[key], "type"):
            subtype = attr[key].type
            if subtype:
                name = "{}.{}".format(name, key)
                # print("{} :: {}".format(name, subtype))
                subobject = from_speckle_object(attr[key], scale, name)
                add_custom_properties(attr[key], subobject)

                subobjects.append(subobject)
                props = attr[key].get("properties", None)
                if props:
                    subobjects.extend(get_speckle_subobjects(props, scale, name))
    return subobjects


ignored_keys = [
    "speckle",
    "_speckle_type",
    "_speckle_name",
    "_speckle_transform",
    "_RNA_UI",
    "transform",
    "_units",
    "_chunkable",
]


def get_blender_custom_properties(obj, max_depth=1000):
    global ignored_keys

    if max_depth < 0:
        return obj

    if hasattr(obj, "keys"):
        d = {}
        for key in obj.keys():
            if key in ignored_keys or key.startswith("_"):
                continue
            d[key] = get_blender_custom_properties(obj[key], max_depth - 1)
        return d
    elif (
        isinstance(obj, list)
        or isinstance(obj, tuple)
        or isinstance(obj, idprop.types.IDPropertyArray)
    ):
        return [get_blender_custom_properties(o, max_depth - 1) for o in obj]
    else:
        return obj


def to_speckle_object(blender_object, scale):
    blender_type = blender_object.type
    speckle_objects = []

    if blender_type in TO_SPECKLE.keys():
        converted = TO_SPECKLE[blender_type](blender_object, blender_object.data, scale)
        if isinstance(converted, list):
            speckle_objects.extend([c for c in converted if c != None])

    for so in speckle_objects:
        so.properties = get_blender_custom_properties(blender_object)

        # Set object transform
        so.properties["transform"] = [y for x in blender_object.matrix_world for y in x]

    # _report(speckle_objects)
    return speckle_objects
