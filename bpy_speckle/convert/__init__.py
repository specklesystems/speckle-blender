from typing import Union
from bpy_speckle.convert.to_native import convert_to_native
from specklepy.objects.base import Base

def get_speckle_subobjects(attr: Union[dict, Base], scale: float, name: str) -> list:
    subobjects = []
    keys = attr.keys() if isinstance(attr, dict) else attr.get_dynamic_member_names()
    for key in keys:
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
