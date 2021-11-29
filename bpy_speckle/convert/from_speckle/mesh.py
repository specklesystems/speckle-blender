import bpy, bmesh, struct
import base64
from bpy_speckle.functions import _report


def add_vertices(smesh, bmesh, scale=1.0):
    sverts = smesh.vertices

    if sverts and len(sverts) > 0:
        for i in range(0, len(sverts), 3):
            bmesh.verts.new(
                (
                    float(sverts[i]) * scale,
                    float(sverts[i + 1]) * scale,
                    float(sverts[i + 2]) * scale,
                )
            )

    bmesh.verts.ensure_lookup_table()


def add_faces(smesh, bmesh, smooth=False):
    sfaces = smesh.faces

    if sfaces and len(sfaces) > 0:
        i = 0
        while i < len(sfaces):
            n = sfaces[i]
            if n < 3:
                n += 3  # 0 -> 3, 1 -> 4

            i += 1
            try:
                f = bmesh.faces.new([bmesh.verts[int(x)] for x in sfaces[i : i + n]])
                f.smooth = smooth
            except Exception as e:
                _report(f"Failed to create face for mesh {smesh.id} \n{e}")
            i += n

        bmesh.faces.ensure_lookup_table()
        bmesh.verts.index_update()


def add_colors(smesh, bmesh):

    scolors = smesh.colors

    if scolors:
        colors = []
        if len(scolors) > 0:

            for i in range(len(scolors)):
                col = int(scolors[i])
                (a, r, g, b) = [
                    int(x) for x in struct.unpack("!BBBB", struct.pack("!i", col))
                ]
                colors.append(
                    (
                        float(r) / 255.0,
                        float(g) / 255.0,
                        float(b) / 255.0,
                        float(a) / 255.0,
                    )
                )

        # Make vertex colors
        if len(scolors) == len(bmesh.verts):
            color_layer = bmesh.loops.layers.color.new("Col")

            for face in bmesh.faces:
                for loop in face.loops:
                    loop[color_layer] = colors[loop.vert.index]


def add_uv_coords(smesh, bmesh):
    if not hasattr(smesh, "properties"):
        return

    sprops = smesh.properties
    if sprops:
        texKey = ""
        if "texture_coordinates" in sprops.keys():
            texKey = "texture_coordinates"
        elif "TextureCoordinates" in sprops.keys():
            texKey = "TextureCoordinates"

        if texKey != "":

            try:
                decoded = base64.b64decode(sprops[texKey]).decode("utf-8")
                s_uvs = decoded.split()
                uv = []

                if int(len(s_uvs) / 2) == len(bmesh.verts):
                    for i in range(0, len(s_uvs), 2):
                        uv.append((float(s_uvs[i]), float(s_uvs[i + 1])))
                else:
                    print(len(s_uvs) * 2)
                    print(len(bmesh.verts))
                    print("Failed to match UV coordinates to vert data.")

                # Make UVs
                uv_layer = bmesh.loops.layers.uv.verify()

                for f in bmesh.faces:
                    for l in f.loops:
                        luv = l[uv_layer]
                        luv.uv = uv[l.vert.index]
            except:
                print("Failed to decode texture coordinates.")
                raise

            del smesh.properties[texKey]


def to_bmesh(speckle_mesh, blender_mesh, name="SpeckleMesh", scale=1.0):
    bm = bmesh.new()

    add_vertices(speckle_mesh, bm, scale)
    add_faces(speckle_mesh, bm)
    add_colors(speckle_mesh, bm)
    add_uv_coords(speckle_mesh, bm)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(blender_mesh)
    bm.free()

    return blender_mesh


def import_mesh(speckle_mesh, scale=1.0, name=None):
    """
    Convert Mesh object
    """
    if not name:
        name = speckle_mesh.geometryHash or speckle_mesh.id

    if name in bpy.data.meshes.keys():
        mesh = bpy.data.meshes[name]
    else:
        mesh = bpy.data.meshes.new(name=name)

    to_bmesh(speckle_mesh, mesh, name, scale)

    return mesh
