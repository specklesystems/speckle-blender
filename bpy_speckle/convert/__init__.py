from bpy_speckle.convert.to_native import convert_to_native


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
