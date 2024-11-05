import math
from typing import Any, Dict, Optional, Tuple, Union, cast

import bpy
import idprop
from bmesh.types import BMesh
from bpy.types import Collection as BCollection
from bpy.types import Material, Node, Object, ShaderNodeVertexColor
from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh
from specklepy.objects.graph_traversal.traversal import TraversalContext
from specklepy.objects.other import RenderMaterial

from bpy_speckle.convert.constants import IGNORED_PROPERTY_KEYS
from bpy_speckle.functions import _report


class ConversionSkippedException(Exception):
    pass


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


def set_custom_property(key: str, value: Any, blender_object: Object) -> None:
    try:
        # Expected c types: float, int, string, float[], int[]
        blender_object[key] = value
    except (OverflowError, TypeError) as ex:
        print(
            f"Skipping setting property ({key}={value}) on {blender_object.name_full}, Reason: {ex}"
        )
    except Exception as ex:
        # TODO: Log this as it's unexpected!!!
        print(
            f"Skipping setting property ({key}={value}) on {blender_object.name_full}, Reason: {ex}"
        )


def add_custom_properties(speckle_object: Base, blender_object: Object):
    if blender_object is None:
        return

    blender_object["_speckle_type"] = type(speckle_object).__name__

    app_id = getattr(speckle_object, "applicationId", None)
    if app_id:
        blender_object["applicationId"] = speckle_object.applicationId
    keys = (
        speckle_object.get_dynamic_member_names()
        if "Geometry" in speckle_object.speckle_type
        else (set(speckle_object.get_member_names()) - IGNORED_PROPERTY_KEYS)
    )
    for key in keys:
        val = getattr(speckle_object, key, None)
        if val is None:
            continue

        if isinstance(val, (int, str, float)):
            set_custom_property(key, val, blender_object)
        elif key == "properties" and isinstance(val, Base):
            val["applicationId"] = None
            add_custom_properties(val, blender_object)
        elif isinstance(val, list):
            items = [item for item in val if not isinstance(item, Base)]
            if items:
                set_custom_property(key, items, blender_object)
        elif isinstance(val, dict):
            for k, v in val.items():
                if not isinstance(v, Base):
                    set_custom_property(k, v, blender_object)


def render_material_to_native(speckle_mat: RenderMaterial) -> Material:
    mat_name = speckle_mat.name
    if not mat_name:
        mat_name = speckle_mat.applicationId or speckle_mat.id or speckle_mat.get_id()

    blender_mat = bpy.data.materials.get(mat_name)
    if blender_mat is None:
        blender_mat = bpy.data.materials.new(mat_name)

        # for now, we're not updating these materials. as per tom's suggestion, we should have a toggle
        # that enables this as the blender mats will prob be much more complex than whatever is coming in
        blender_mat.use_nodes = True
        inputs = blender_mat.node_tree.nodes["Principled BSDF"].inputs

        inputs["Base Color"].default_value = to_rgba(speckle_mat.diffuse)  # type: ignore
        inputs["Roughness"].default_value = speckle_mat.roughness  # type: ignore
        inputs["Metallic"].default_value = speckle_mat.metalness  # type: ignore
        inputs["Alpha"].default_value = speckle_mat.opacity  # type: ignore

        # Blender >=4.0 use "Emission Color"
        emission_color = "Emission" if "Emission" in inputs else "Emission Color"  # type: ignore
        inputs[emission_color].default_value = to_rgba(speckle_mat.emissive)  # type: ignore

    if speckle_mat.opacity < 1.0:
        blender_mat.blend_method = "BLEND"

    return blender_mat


_vertex_color_material: Optional[Material] = None


def get_vertex_color_material() -> Material:
    global _vertex_color_material

    # see https://stackoverflow.com/a/69807985
    if not _vertex_color_material:
        _vertex_color_material = bpy.data.materials.new("Vertex Color Material")
        _vertex_color_material.use_nodes = True
        nodes = _vertex_color_material.node_tree.nodes
        principled_bsdf_node = cast(Node, nodes.get("Principled BSDF"))

        if "VERTEX_COLOR" not in [node.type for node in nodes]:
            vertex_color_node = cast(
                ShaderNodeVertexColor, nodes.new(type="ShaderNodeVertexColor")
            )
        else:
            vertex_color_node = cast(ShaderNodeVertexColor, nodes.get("Vertex Color"))
        vertex_color_node.layer_name = "Col"

        links = _vertex_color_material.node_tree.links
        _ = links.new(vertex_color_node.outputs[0], principled_bsdf_node.inputs[0])

    return _vertex_color_material


def get_render_material(speckle_object: Base) -> Optional[RenderMaterial]:
    """Trys to get a RenderMaterial on given speckle_object"""

    speckle_mat = getattr(
        speckle_object,
        "renderMaterial",
        getattr(speckle_object, "@renderMaterial", None),
    )

    if isinstance(speckle_mat, RenderMaterial):
        return speckle_mat

    return None


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


def add_faces(
    speckle_mesh: Mesh,
    blender_mesh: BMesh,
    indexOffset: int,
    materialIndex: int = 0,
    smooth: bool = True,
):
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
                argb = int(scolors[i])
                (a, r, g, b) = argb_split(argb)
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


def argb_split(argb: int) -> Tuple[int, int, int, int]:
    alpha = (argb >> 24) & 0xFF
    red = (argb >> 16) & 0xFF
    green = (argb >> 8) & 0xFF
    blue = argb & 0xFF

    return (alpha, red, green, blue)


def add_uv_coords(speckle_mesh: Mesh, blender_mesh: BMesh):
    s_uvs = speckle_mesh.textureCoordinates
    if not s_uvs:
        return
    try:
        uv = []

        if len(s_uvs) // 2 == len(blender_mesh.verts):
            uv.extend(
                (float(s_uvs[i]), float(s_uvs[i + 1])) for i in range(0, len(s_uvs), 2)
            )
        else:
            _report(
                f"Failed to match UV coordinates to vert data. Blender mesh verts: {len(blender_mesh.verts)}, Speckle UVs: {len(s_uvs) // 2}"
            )
            return

        # Make UVs
        uv_layer = blender_mesh.loops.layers.uv.verify()

        for f in blender_mesh.faces:
            for loop in f.loops:
                luv = loop[uv_layer]
                luv.uv = uv[loop.vert.index]
    except:
        _report("Failed to decode texture coordinates.")
        raise


ignored_keys = {
    "id",
    "speckle",
    "speckle_type" "_speckle_type",
    "_speckle_name",
    "_speckle_transform",
    "_RNA_UI",
    "elements",
    "transform",
    "_units",
    "_chunkable",
}


def get_blender_custom_properties(obj, max_depth: int = 63):
    """Recursively grabs custom properties on blender objects. Max depth is determined by the max allowed by Newtonsoft.NET, don't exceed unless you know what you're doing"""
    if max_depth <= 0:
        return obj

    if hasattr(obj, "keys"):
        keys = set(obj.keys()) - ignored_keys
        return {
            key: get_blender_custom_properties(obj[key], max_depth - 1)
            for key in keys
            if not key.startswith("_")
        }

    if isinstance(obj, (list, tuple, idprop.types.IDPropertyArray)):
        return [get_blender_custom_properties(o, max_depth - 1) for o in obj]  # type: ignore

    return obj


"""
Python implementation of Blender's NURBS curve generation for to Speckle conversion
from: https://blender.stackexchange.com/a/34276
based on https://projects.blender.org/blender/blender/src/branch/main/source/blender/blenkernel/intern/curve.cc (check old version)
"""


def macro_knotsu(nu: bpy.types.Spline) -> int:
    return nu.order_u + nu.point_count_u + (nu.order_u - 1 if nu.use_cyclic_u else 0)


def macro_segmentsu(nu: bpy.types.Spline) -> int:
    return nu.point_count_u if nu.use_cyclic_u else nu.point_count_u - 1


def make_knots(nu: bpy.types.Spline) -> list[float]:
    knots = [0.0] * macro_knotsu(nu)
    flag = nu.use_endpoint_u + (nu.use_bezier_u << 1)
    if nu.use_cyclic_u:
        calc_knots(knots, nu.point_count_u, nu.order_u, 0)
    else:
        calc_knots(knots, nu.point_count_u, nu.order_u, flag)
    return knots


def calc_knots(knots: list[float], point_count: int, order: int, flag: int) -> None:
    pts_order = point_count + order
    if flag == 1:  # CU_NURB_ENDPOINT
        k = 0.0
        for a in range(1, pts_order + 1):
            knots[a - 1] = k
            if a >= order and a <= point_count:
                k += 1.0
    elif flag == 2:  # CU_NURB_BEZIER
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
        for a in range(1, len(knots) - 1):
            knots[a] = a - 1

        knots[-1] = knots[-2]


def basis_nurb(
    t: float,
    order: int,
    point_count: int,
    knots: list[float],
    basis: list[float],
    start: int,
    end: int,
) -> Tuple[int, int]:
    i1 = i2 = 0
    orderpluspnts = order + point_count
    opp2 = orderpluspnts - 1

    # this is for float inaccuracy
    if t < knots[0]:
        t = knots[0]
    elif t > knots[opp2]:
        t = knots[opp2]

    # this part is order '1'
    o2 = order + 1
    for i in range(opp2):
        if knots[i] != knots[i + 1] and t >= knots[i] and t <= knots[i + 1]:
            basis[i] = 1.0
            i1 = i - o2
            if i1 < 0:
                i1 = 0
            i2 = i
            i += 1
            while i < opp2:
                basis[i] = 0.0
                i += 1
            break

        else:
            basis[i] = 0.0

    basis[i] = 0.0  # type: ignore

    # this is order 2, 3, ...
    for j in range(2, order + 1):
        if i2 + j >= orderpluspnts:
            i2 = opp2 - j

        for i in range(i1, i2 + 1):
            if basis[i] != 0.0:
                d = ((t - knots[i]) * basis[i]) / (knots[i + j - 1] - knots[i])
            else:
                d = 0.0

            if basis[i + 1] != 0.0:
                e = ((knots[i + j] - t) * basis[i + 1]) / (knots[i + j] - knots[i + 1])
            else:
                e = 0.0

            basis[i] = d + e

    start = 1000
    end = 0

    for i in range(i1, i2 + 1):
        if basis[i] > 0.0:
            end = i
            if start == 1000:
                start = i

    return start, end


def nurb_make_curve(nu: bpy.types.Spline, resolu: int, stride: int = 3) -> list[float]:
    """ "BKE_nurb_makeCurve"""
    EPS = 1e-6
    coord_index = istart = iend = 0

    coord_array = [0.0] * (3 * nu.resolution_u * macro_segmentsu(nu))
    sum_array = [0] * nu.point_count_u
    basisu = [0.0] * macro_knotsu(nu)
    knots = make_knots(nu)

    resolu = resolu * macro_segmentsu(nu)
    ustart = knots[nu.order_u - 1]
    uend = (
        knots[nu.point_count_u + nu.order_u - 1]
        if nu.use_cyclic_u
        else knots[nu.point_count_u]
    )
    ustep = (uend - ustart) / (resolu - (0 if nu.use_cyclic_u else 1))
    cycl = nu.order_u - 1 if nu.use_cyclic_u else 0

    u = ustart
    while resolu:
        resolu -= 1
        istart, iend = basis_nurb(
            u, nu.order_u, nu.point_count_u + cycl, knots, basisu, istart, iend
        )

        # /* calc sum */
        sumdiv = 0.0
        sum_index = 0
        pt_index = istart - 1
        for i in range(istart, iend + 1):
            if i >= nu.point_count_u:
                pt_index = i - nu.point_count_u
            else:
                pt_index += 1

            sum_array[sum_index] = basisu[i] * nu.points[pt_index].co[3]  # type: ignore
            sumdiv += sum_array[sum_index]
            sum_index += 1

        if (sumdiv != 0.0) and (sumdiv < 1.0 - EPS or sumdiv > 1.0 + EPS):
            sum_index = 0
            for i in range(istart, iend + 1):
                sum_array[sum_index] /= sumdiv  # type: ignore
                sum_index += 1

        coord_array[coord_index : coord_index + 3] = (0.0, 0.0, 0.0)

        sum_index = 0
        pt_index = istart - 1
        for i in range(istart, iend + 1):
            if i >= nu.point_count_u:
                pt_index = i - nu.point_count_u
            else:
                pt_index += 1

            if sum_array[sum_index] != 0.0:
                for j in range(3):
                    coord_array[coord_index + j] += (
                        sum_array[sum_index] * nu.points[pt_index].co[j]
                    )
            sum_index += 1

        coord_index += stride
        u += ustep

    return coord_array


def link_object_to_collection_nested(obj: Object, col: BCollection):
    if obj.name not in col.objects:  # type: ignore
        col.objects.link(obj)

    for child in obj.children:
        link_object_to_collection_nested(child, col)


def add_to_hierarchy(
    converted: Union[Object, BCollection],
    traversalContext: "TraversalContext",
    converted_objects: Dict[str, Union[Object, BCollection]],
    preserve_transform: bool,
) -> None:
    nextParent = traversalContext.parent

    # Traverse up the tree to find a direct parent object, and a containing collection
    parent_collection: Optional[BCollection] = None
    parent_object: Optional[Object] = None

    while nextParent:
        if nextParent.current.id in converted_objects:
            c = converted_objects[nextParent.current.id]

            if isinstance(c, BCollection):
                parent_collection = c
                break
            else:  # isinstance(c, Object):
                parent_object = parent_object or c

        nextParent = nextParent.parent

    # If no containing collection is found, fall back to the scene collection
    if not parent_collection:
        parent_collection = bpy.context.scene.collection

    if isinstance(converted, Object):
        if parent_object:
            set_parent(converted, parent_object, preserve_transform)
        link_object_to_collection_nested(converted, parent_collection)
    elif converted.name not in parent_collection.children.keys():
        parent_collection.children.link(converted)


def set_parent(child: Object, parent: Object, preserve_transform: bool = False) -> None:
    if preserve_transform:
        previous = child.matrix_world.copy()  # type: ignore
        child.parent = parent
        child.matrix_world = previous
    else:
        child.parent = parent
