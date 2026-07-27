import bpy
from bpy.types import ID, Object
from bpy.types import Mesh as BMesh
import math
from contextlib import contextmanager
from typing import Tuple, Optional, Dict, Any, Iterator

OBJECT_NAME_SPECKLE_SEPARATOR = " -- "
SPECKLE_ID_LENGTH = 32
_QUICK_TEST_NAME_LENGTH = SPECKLE_ID_LENGTH + len(OBJECT_NAME_SPECKLE_SEPARATOR)


def to_speckle_name(blender_object: bpy.types.ID) -> str:
    does_name_contain_id = (
        len(blender_object.name) > _QUICK_TEST_NAME_LENGTH
        and OBJECT_NAME_SPECKLE_SEPARATOR in blender_object.name
    )
    if does_name_contain_id:
        return blender_object.name.rsplit(OBJECT_NAME_SPECKLE_SEPARATOR, 1)[0]
    else:
        return blender_object.name


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


def get_unique_id(native_object: ID, suffix: Optional[str] = None) -> str:
    base_id = f"{type(native_object).__name__}:{native_object.name_full}"

    if suffix:
        return f"{base_id}:{suffix}"

    return base_id


def get_object_id(blender_object: Object) -> str:
    return get_unique_id(blender_object)


# Geometry ids are keyed on the OBJECT, never on its data-block. Every displayValue
# is baked into world coordinates (the direct-display dialect), so two objects
# sharing one data-block — linked duplicates — describe *different* geometry. A
# data-block key made those ids collide, and the bundle exporter's id-keyed
# geometry cache then served every duplicate the first one's world-space mesh, so
# they all rendered stacked at the first duplicate's transform. Same convention as
# the C# connectors' `{objectAppId}:g{ord}`.


def get_submesh_id(blender_object: Object, material_index: int) -> str:
    return f"{get_object_id(blender_object)}:mat{material_index}"


def get_curve_element_id(blender_object: Object, curve_index: int = 0) -> str:
    return f"{get_object_id(blender_object)}:curve{curve_index}"


def extract_custom_properties(blender_id: ID) -> Dict[str, Any]:
    """
    Extract custom user-defined properties from a Blender ID datablock.

    Supports strings, ints, floats, bools, and arrays of these types.
    Note: on the parquet-bundle path arrays are dropped by the eav
    flattener (scalars and nested dicts only); they still serialize on
    the classic send path.
    """
    properties: Dict[str, Any] = {}

    for key in blender_id.keys():
        # skip system properties that start with underscore (e.g. _RNA_UI)
        if key.startswith("_"):
            continue

        try:
            value = blender_id[key]

            if isinstance(value, (str, int, float, bool)):
                properties[key] = value
            elif isinstance(value, (list, tuple)):
                if all(isinstance(item, (str, int, float, bool)) for item in value):
                    properties[key] = list(value)
            elif type(value).__name__ == "IDPropertyArray":
                # Blender IDPropertyArray (bool/int/float arrays)
                try:
                    array_list = (
                        value.to_list() if hasattr(value, "to_list") else list(value)
                    )
                    if all(
                        isinstance(item, (str, int, float, bool)) for item in array_list
                    ):
                        properties[key] = array_list
                except (TypeError, ValueError):
                    continue
        except (KeyError, TypeError):
            # skip properties that can't be accessed or have unsupported types
            continue

    return properties


def apply_cached_properties(speckle_obj, properties: Dict[str, Any]) -> None:
    """Apply pre-extracted custom properties to a Speckle object if they exist."""
    if properties:
        speckle_obj.properties = properties


def has_cross_object_geometry_deps(blender_data: Optional[ID]) -> bool:
    """Whether a Curve/TextCurve datablock builds its surface from *other*
    objects — ``bevel_object`` (a curve used as the swept cross-section) or
    ``taper_object`` (a curve scaling that section along the path).

    Those references are resolved by the depsgraph and nothing else: calling
    ``to_mesh()`` on the original object returns zero faces, with or without a
    ``depsgraph=`` argument (measured on Blender 4.3). Only
    ``evaluated_get(depsgraph).to_mesh()`` produces the surface.
    """
    if blender_data is None:
        return False

    return bool(
        getattr(blender_data, "bevel_object", None)
        or getattr(blender_data, "taper_object", None)
    )


def needs_evaluated_object(blender_object: Object, apply_modifiers: bool) -> bool:
    """Whether tessellation has to go through the depsgraph-evaluated copy.

    Modifiers are the obvious case. The subtler one is a curve whose profile
    lives on another object: there is no un-evaluated route to that surface, so
    the choice is between evaluating (and inheriting modifiers the caller asked
    us to skip) or publishing no faces at all.

    TODO: confirm the behaviour when ``apply_modifiers`` is False *and* the
    curve has a bevel/taper object. Options:
      - evaluate anyway (current): the profile is honoured, so the published
        tube matches the viewport, but any modifiers ride along against the
        caller's wish. Only affects curves that have both.
      - respect the flag: return False here, tessellation finds no faces and
        the curve falls back to publishing its path as a wire. Honest about
        the setting, but the user sees a line where Blender shows a solid.
    """
    if apply_modifiers and blender_object.modifiers:
        return True

    return has_cross_object_geometry_deps(blender_object.data)


@contextmanager
def temporary_mesh(
    blender_object: Object, apply_modifiers: bool
) -> Iterator[Optional[BMesh]]:
    """Yield the tessellated mesh of ``blender_object``, freeing it afterwards.

    Used by every object type that has no Speckle geometry primitive of its own
    (text, bevelled/extruded curves) and therefore has to reach the viewer as
    triangles. Blender already tessellates these for the viewport, so we borrow
    that result instead of reimplementing the sweep or the fill.

    ``to_mesh()`` hands back a mesh owned by the object it was called on, so the
    matching ``to_mesh_clear()`` has to target that same object — the evaluated
    copy when we went through the depsgraph, the original otherwise.
    """
    source = blender_object
    if needs_evaluated_object(blender_object, apply_modifiers):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        source = blender_object.evaluated_get(depsgraph)

    mesh: Optional[BMesh] = None
    try:
        mesh = source.to_mesh()
    except RuntimeError:
        # object state that Blender refuses to tessellate
        mesh = None

    try:
        yield mesh
    finally:
        if mesh is not None:
            source.to_mesh_clear()
