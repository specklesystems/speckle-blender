import bpy
import math
from typing import Tuple

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
