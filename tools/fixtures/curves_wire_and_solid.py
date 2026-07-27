"""Curve dialect fixture: a wire curve and a solid curve in one scene.

Guards the split introduced in "Publish solid curves as tessellated meshes":
``curve_may_have_volume`` decides whether an object publishes as tessellated
mesh geometry or keeps its exact spline definition. Both look plausible in the
viewer — a tube and a wire are both "a curve" at a glance — so the only reliable
check is which geometry type each one actually produced.
"""

import bpy


def _bezier(name, solid):
    curve = bpy.data.curves.new(f"{name}Curve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(2)
    for i, point in enumerate(spline.bezier_points):
        point.co = (float(i), float(i % 2), 0.0)
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"

    if solid:
        # a round cross-section swept along the path -> Blender generates faces
        curve.bevel_mode = "ROUND"
        curve.bevel_depth = 0.1

    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build():
    return [_bezier("WireCurve", solid=False), _bezier("SolidCurve", solid=True)]


EXPECT = {
    "objects": 2,
    # exactly one of each: the solid tessellates to a mesh, the wire stays a curve
    "geometry_types": {"mesh": 1, "curve": 1},
    "relations": {"DISPLAY": 2, "IN_COLLECTION": 2},
    "properties": {
        "WireCurve": {"name": "WireCurve", "type": "CURVE"},
        "SolidCurve": {"name": "SolidCurve", "type": "CURVE"},
    },
}
