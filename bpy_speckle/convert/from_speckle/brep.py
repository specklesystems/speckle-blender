import bpy
from .mesh import to_bmesh
from bpy_speckle.util import find_key_case_insensitive


def import_brep(speckle_brep, scale, name=None):
    if not name:
        name = speckle_brep.geometryHash or speckle_brep.id

    display = getattr(
        speckle_brep, "displayMesh", getattr(speckle_brep, "displayValue", None)
    )
    if display:
        if name in bpy.data.meshes.keys():
            mesh = bpy.data.meshes[name]
        else:
            mesh = bpy.data.meshes.new(name=name)

        to_bmesh(display, mesh, name, scale)
        # add_custom_properties(speckle_brep[dvKey], mesh)
    else:
        mesh = None

    return mesh
