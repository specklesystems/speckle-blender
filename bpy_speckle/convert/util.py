import math
from typing import Tuple
from bmesh.types import BMesh
import bpy, struct, idprop

from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh
from bpy_speckle.functions import _report
from bpy.types import Object

IGNORED_PROPERTY_KEYS = {
    "id",
    "elements",
    "displayMesh",
    "displayValue",
    "speckle_type",
    "parameters",
    "faces",
    "colors",
    "vertices",
    "renderMaterial",
    "textureCoordinates",
    "totalChildrenCount"
}


def to_rgba(argb_int: int) -> Tuple[float, float, float, float]:
    """Converts the int representation of a colour into a percent RGBA tuple"""
    alpha = ((argb_int >> 24) & 255) / 255
    red = ((argb_int >> 16) & 255) / 255
    green = ((argb_int >> 8) & 255) / 255
    blue = (argb_int & 255) / 255

    return (red, green, blue, alpha)


def to_argb_int(rgba_color: list[float]) -> int:
    """Converts an RGBA array to an ARGB integer"""
    argb_color = rgba_color[-1:] + rgba_color[:3]
    int_color = [int(val * 255) for val in argb_color]

    return int.from_bytes(int_color, byteorder="big", signed=True)

def add_custom_properties(speckle_object: Base, blender_object: Object):
    if blender_object is None:
        return

    blender_object["_speckle_type"] = type(speckle_object).__name__

    app_id = getattr(speckle_object, "applicationId", None)
    if app_id:
        blender_object["applicationId"] = speckle_object.applicationId
    keys = speckle_object.get_dynamic_member_names() if "Geometry" in speckle_object.speckle_type else (set(speckle_object.get_member_names()) - IGNORED_PROPERTY_KEYS)
    for key in keys:
        val = getattr(speckle_object, key, None)
        if val is None:
            continue

        if isinstance(val, (int, str, float)):
            blender_object[key] = val
        elif key == "properties" and isinstance(val, Base):
            val["applicationId"] = None
            add_custom_properties(val, blender_object)
        elif isinstance(val, list):
            items = [item for item in val if not isinstance(item, Base)]
            if items:
                blender_object[key] = items
        elif isinstance(val,dict):
            for (k,v) in val.items():
                if not isinstance(v, Base):
                    blender_object[k] = v            


def add_blender_material(speckle_object: Base, blender_object: Object) -> None:
    """Add material to a blender object if the corresponding speckle object has a render material"""
    if blender_object.data is None:
        return

    speckle_mat = getattr(
        speckle_object,
        "renderMaterial",
        getattr(speckle_object, "@renderMaterial", None),
    )
    if not speckle_mat:
        return

    mat_name = getattr(speckle_mat, "name", None) or speckle_mat.__dict__.get("@name")
    if not mat_name:
        mat_name = speckle_mat.applicationId or speckle_mat.id or speckle_mat.get_id()

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


def add_vertices(speckle_mesh: Mesh, blender_mesh: BMesh, scale=1.0):
    sverts = speckle_mesh.vertices

    if sverts and len(sverts) > 0:
        for i in range(0, len(sverts), 3):
            blender_mesh.verts.new(
                (
                    float(sverts[i]) * scale,
                    float(sverts[i + 1]) * scale,
                    float(sverts[i + 2]) * scale,
                )
            )



def add_faces(speckle_mesh: Mesh, blender_mesh: BMesh, indexOffset: int, materialIndex: int = 0, smooth:bool = False):
    sfaces = speckle_mesh.faces
    
    if sfaces and len(sfaces) > 0:
        i = 0
        while i < len(sfaces):
            n = sfaces[i]
            if n < 3:
                n += 3  # 0 -> 3, 1 -> 4

            i += 1
            try:
                f = blender_mesh.faces.new(
                    [blender_mesh.verts[x + indexOffset] for x in sfaces[i : i + n]]
                )
                f.material_index = materialIndex
                f.smooth = smooth
            except Exception as e:
                _report(f"Failed to create face for mesh {speckle_mesh.id} \n{e}")
            i += n


def add_colors(speckle_mesh: Mesh, blender_mesh: BMesh):

    scolors = speckle_mesh.colors

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
        if len(scolors) == len(blender_mesh.verts):
            color_layer = blender_mesh.loops.layers.color.new("Col")

            for face in blender_mesh.faces:
                for loop in face.loops:
                    loop[color_layer] = colors[loop.vert.index]


def add_uv_coords(speckle_mesh: Mesh, blender_mesh: BMesh):
    s_uvs = speckle_mesh.textureCoordinates
    if not s_uvs:
        return
    try:
        uv = []

        if len(s_uvs) // 2 == len(blender_mesh.verts):
            uv.extend(
                (float(s_uvs[i]), float(s_uvs[i + 1]))
                for i in range(0, len(s_uvs), 2)
            )
        else:
            _report(
                f"Failed to match UV coordinates to vert data. Blender mesh verts: {len(blender_mesh.verts)}, Speckle UVs * 2: {len(s_uvs) * 2}"
            )
            return

        # Make UVs
        uv_layer = blender_mesh.loops.layers.uv.verify()

        for f in blender_mesh.faces:
            for l in f.loops:
                luv = l[uv_layer]
                luv.uv = uv[l.vert.index]
    except:
        _report("Failed to decode texture coordinates.")
        raise


ignored_keys = {
    "id",
    "speckle",
    "speckle_type"
    "_speckle_type",
    "_speckle_name",
    "_speckle_transform",
    "_RNA_UI",
    "elements",
    "transform",
    "_units",
    "_chunkable",
}

def get_blender_custom_properties(obj, max_depth=1000):
    if max_depth < 0:
        return obj

    if hasattr(obj, "keys"):
        keys = set(obj.keys()) - ignored_keys
        return {
            key: get_blender_custom_properties(obj[key], max_depth - 1)
            for key in keys
            if not key.startswith("_")
        }

    if isinstance(obj, (list, tuple, idprop.types.IDPropertyArray)):
        return [get_blender_custom_properties(o, max_depth - 1) for o in obj]
    
    return obj


"""
Python implementation of Blender's NURBS curve generation for to Speckle conversion
from: https://blender.stackexchange.com/a/34276
"""


def macro_knotsu(nu: bpy.types.Spline) -> int:
    return nu.order_u + nu.point_count_u + (nu.order_u - 1 if nu.use_cyclic_u else 0)


def macro_segmentsu(nu: bpy.types.Spline) -> int:
    return nu.point_count_u if nu.use_cyclic_u else nu.point_count_u - 1


def make_knots(nu: bpy.types.Spline) -> list[float]:
    knots = [0.0] * (4 + macro_knotsu(nu))
    flag = nu.use_endpoint_u + (nu.use_bezier_u << 1)
    if nu.use_cyclic_u:
        calc_knots(knots, nu.point_count_u, nu.order_u, 0)
        makecyclicknots(knots, nu.point_count_u, nu.order_u)
    else:
        calc_knots(knots, nu.point_count_u, nu.order_u, flag)
    return knots


def calc_knots(knots: list[float], point_count: int, order: int, flag: int) -> None:
    pts_order = point_count + order
    if flag == 1:
        k = 0.0
        for a in range(1, pts_order + 1):
            knots[a - 1] = k
            if a >= order and a <= point_count:
                k += 1.0
    elif flag == 2:
        if order == 4:
            k = 0.34
            for a in range(pts_order):
                knots[a] = math.floor(k)
                k += 1.0 / 3.0
        elif order == 3:
            k = 0.6
            for a in range(pts_order):
                if a >= order and a <= point_count:
                    k += 0.5
                    knots[a] = math.floor(k)
    else:
        for a in range(pts_order):
            knots[a] = a


def makecyclicknots(knots: list[float], point_count: int, order: int) -> None:
    order2 = order - 1

    if order > 2:
        b = point_count + order2
        for a in range(1, order2):
            if knots[b] != knots[b - a]:
                break

            if a == order2:
                knots[point_count + order - 2] += 1.0

    b = order
    c = point_count + order + order2
    for a in range(point_count + order2, c):
        knots[a] = knots[a - 1] + (knots[b] - knots[b - 1])
        b -= 1
