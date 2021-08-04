import bpy, idprop
from mathutils import Matrix

from .from_speckle import *
from .to_speckle import *
from .util import *
from bpy_speckle.functions import _report, get_scale_length

from specklepy.objects.geometry import *
from specklepy.objects.other import RenderMaterial

from devtools import debug

FROM_SPECKLE_SCHEMAS = {
    Mesh: import_mesh,
    Brep: import_brep,
    Curve: import_curve,
    Line: import_curve,
    Polyline: import_curve,
    Polycurve: import_curve,
    Arc: import_curve,
}


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

    if transform and len(transform) == 16:
        mat = Matrix(
            [transform[0:4], transform[4:8], transform[8:12], transform[12:16]]
        )
        blender_object.matrix_world = mat


def add_blender_material(smesh, blender_object) -> None:
    """Add material to a blender object if the corresponding speckle object has a render material"""
    if blender_object.data is None:
        return

    if not hasattr(smesh, "renderMaterial") and not hasattr(smesh, "@renderMaterial"):
        return

    speckle_mat = getattr(smesh, "renderMaterial", None) or smesh["@renderMaterial"]
    mat_name = getattr(speckle_mat, "name", None) or speckle_mat.__dict__.get("@name")
    if not mat_name:
        mat_name = speckle_mat.applicationId or speckle_mat.id

    blender_mat = bpy.data.materials.get(mat_name)
    if not blender_mat:
        blender_mat = bpy.data.materials.new(mat_name)

        # for now, we're not updating these materials. as per tom's suggestion, we should have a toggle
        # that enables this as the blender mats will prob be much more complex than whatever is coming in
        blender_mat.use_nodes = True
        inputs = blender_mat.node_tree.nodes["Principled BSDF"].inputs

        inputs["Base Color"].default_value = to_rgba(speckle_mat.diffuse)
        inputs["Emission"].default_value = to_rgba(speckle_mat.emissive)
        inputs["Roughness"].default_value = speckle_mat.roughness
        inputs["Metallic"].default_value = speckle_mat.metalness
        inputs["Alpha"].default_value = speckle_mat.opacity

    if speckle_mat.opacity < 1:
        blender_mat.blend_method = "BLEND"

    blender_object.data.materials.append(blender_mat)


def material_to_speckle(blender_object) -> RenderMaterial:
    """Create and return a render material from a blender object"""
    if not getattr(blender_object.data, "materials", None):
        return

    blender_mat = blender_object.data.materials[0]
    speckle_mat = RenderMaterial()
    speckle_mat.name = blender_mat.name

    if blender_mat.use_nodes is True:
        inputs = blender_mat.node_tree.nodes["Principled BSDF"].inputs
        speckle_mat.diffuse = to_argb_int(inputs["Base Color"].default_value)
        speckle_mat.emissive = to_argb_int(inputs["Emission"].default_value)
        speckle_mat.roughness = inputs["Roughness"].default_value
        speckle_mat.metalness = inputs["Metallic"].default_value
        speckle_mat.opacity = inputs["Alpha"].default_value

    else:
        speckle_mat.diffuse = to_argb_int(blender_mat.diffuse_color)
        speckle_mat.metalness = blender_mat.metallic
        speckle_mat.roughness = blender_mat.roughness

    return speckle_mat


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

    ignore = ["_chunkable", "_units", "units"]

    if hasattr(speckle_object, "applicationId"):
        blender_object["applicationId"] = speckle_object.applicationId

    for key in speckle_object.get_dynamic_member_names():
        if key in ignore:
            continue
        if isinstance(speckle_object[key], (int, str, float, dict)):
            blender_object[key] = speckle_object[key]


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
    speckle_name = (
        name
        or getattr(speckle_object, "name", None)
        or speckle_object.speckle_type + f" -- {speckle_object.id}"
    )

    units = getattr(speckle_object, "units", None)
    if units:
        scale = get_scale_length(units) / bpy.context.scene.unit_settings.scale_length

    # try native conversion
    if type(speckle_object) in FROM_SPECKLE_SCHEMAS.keys():
        print("Got object type: {}".format(type(speckle_object)))

        try:
            obdata = FROM_SPECKLE_SCHEMAS[type(speckle_object)](
                speckle_object, scale, speckle_name
            )
        except Exception as e:  # conversion error
            _report(f"Error converting {speckle_object} \n{e}")
            return None

        if speckle_name in bpy.data.objects.keys():
            blender_object = bpy.data.objects[speckle_name]
            blender_object.data = obdata
            blender_object.matrix_world = Matrix()
            if hasattr(obdata, "materials"):
                blender_object.data.materials.clear()
        else:
            blender_object = bpy.data.objects.new(speckle_name, obdata)

        blender_object.speckle.object_id = str(speckle_object.id)
        blender_object.speckle.enabled = True

        add_custom_properties(speckle_object, blender_object)
        add_blender_material(speckle_object, blender_object)
        # TODO: chat with tom re transforms
        # set_transform(speckle_object, blender_object)

        return blender_object

    # try display mesh
    mesh = getattr(
        speckle_object, "displayMesh", getattr(speckle_object, "displayValue", None)
    )
    if mesh:
        return from_speckle_object(mesh, scale, speckle_name)

    # return none if fail
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
        return {
            key: get_blender_custom_properties(obj[key], max_depth - 1)
            for key in obj.keys()
            if key not in ignored_keys and not key.startswith("_")
        }

    elif isinstance(obj, (list, tuple, idprop.types.IDPropertyArray)):
        return [get_blender_custom_properties(o, max_depth - 1) for o in obj]
    else:
        return obj


def to_speckle_object(blender_object, scale):
    blender_type = blender_object.type
    speckle_objects = []
    speckle_material = material_to_speckle(blender_object)

    if blender_type in TO_SPECKLE.keys():
        converted = TO_SPECKLE[blender_type](blender_object, blender_object.data, scale)
        if isinstance(converted, list):
            speckle_objects.extend([c for c in converted if c != None])

    for so in speckle_objects:
        so.properties = get_blender_custom_properties(blender_object)
        so.applicationId = so.properties.pop("applicationId", None)

        if speckle_material:
            so["renderMaterial"] = speckle_material

        # Set object transform
        so.properties["transform"] = [y for x in blender_object.matrix_world for y in x]

    # _report(speckle_objects)
    return speckle_objects
