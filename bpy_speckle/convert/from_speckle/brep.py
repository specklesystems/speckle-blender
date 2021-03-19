import bpy
from .mesh import to_bmesh
from bpy_speckle.util import find_key_case_insensitive

def import_brep(speckle_brep, scale, name=None):
    if not name:
        name = speckle_brep.geometryHash

        if not name:
            name = speckle_brep.id

    if speckle_brep.displayValue:

        if name in bpy.data.meshes.keys():
            mesh = bpy.data.meshes[name]
        else:
            mesh = bpy.data.meshes.new(name=name)        

        to_bmesh(speckle_brep.displayValue, mesh, name, scale)
        #add_custom_properties(speckle_brep[dvKey], mesh)
    else:
        mesh = None

    return mesh