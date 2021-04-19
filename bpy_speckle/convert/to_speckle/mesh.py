import bpy, bmesh, struct

import base64, hashlib
from time import strftime, gmtime

from specklepy.objects.geometry import Mesh, Interval, Box


def export_mesh(blender_object, data, scale=1.0):
    if data.loop_triangles is None or len(data.loop_triangles) < 1:
        data.calc_loop_triangles()

    mat = blender_object.matrix_world

    verts = [tuple(mat @ x.co * scale) for x in data.vertices]

    # TODO: add n-gon support, using tessfaces for now
    # faces = [x.vertices for x in data.loop_triangles]
    faces = [p.vertices for p in data.polygons]
    unit_system = bpy.context.scene.unit_settings.system

    sm = Mesh(
        name=blender_object.name,
        vertices=list(sum(verts, ())),
        faces=[],
        colors=[],
        units="m" if unit_system == "METRIC" else "ft",
        bbox=Box(area=0.0, volume=0.0),
        applicationId="Blender",
    )

    for f in faces:
        if len(f) == 3:
            sm.faces.append(0)
        elif len(f) == 4:
            sm.faces.append(1)
        else:
            continue
        sm.faces.extend(f)

    return [sm]
