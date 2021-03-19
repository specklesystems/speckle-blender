import bpy, bmesh, struct

import base64, hashlib
from time import strftime, gmtime

from speckle.objects.geometry import Mesh

def export_mesh(blender_object, scale=1.0):
    if blender_object.data.loop_triangles is None or len(blender_object.data.loop_triangles) < 1:
        blender_object.data.calc_loop_triangles()
    verts = [x.co * scale for x in blender_object.data.vertices]

    # TODO: add n-gon support, using tessfaces for now
    faces = [x.vertices for x in blender_object.data.loop_triangles]

    sm = Mesh(vertices=[], faces=[])

    for v in verts:
        sm.vertices.extend(v)

    for f in faces:
        if len(f) == 3:
            sm.faces.append(0)
        elif len(f) == 4:
            sm.faces.append(1)
        else:
            continue

        sm.faces.extend(f)

    sm.name = blender_object.name 
    sm.colors = []
    sm.applicationId = "Blender"

    return sm
