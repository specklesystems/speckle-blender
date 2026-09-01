"""Surface dialect fixture: a NURBS patch and a face-less surface object.

Guards the SURFACE publish path. Two things are easy to get wrong here and both
look fine in the viewport:

- A NURBS patch must publish as a *mesh*. Routing it through the curve path
  instead would emit its control rows as loose wires — plausible-looking output
  that is not the surface the user modelled.
- A SURFACE object that tessellates to no faces (Blender's "NURBS Curve" lives
  in a SURFACE object, with a single spline) has no wire fallback on this path,
  so it is dropped. Pinned here so the drop is a documented choice rather than a
  silent surprise.

Built with the ``surface.primitive_nurbs_surface_*`` operators because a patch
is not constructible through the data API alone — splines have to be joined with
``curve.make_segment`` in edit mode, which is the same operator the Add menu
runs.
"""

import bpy


def _add(operator, name):
    operator()
    obj = bpy.context.active_object
    obj.name = name
    return obj


def build():
    patch = _add(bpy.ops.surface.primitive_nurbs_surface_surface_add, "NurbsPatch")
    patch["surface_prop"] = "on-the-object"
    patch["panel_id"] = 7
    # data-block property — dropped by the bundle path, same as every other type
    patch.data["datablock_prop"] = "on-the-datablock"

    # a SURFACE object holding a single spline: no faces, nothing to tessellate
    wire = _add(bpy.ops.surface.primitive_nurbs_surface_curve_add, "SurfaceWire")

    return [patch, wire]


EXPECT = {
    # SurfaceWire tessellates to no faces and is dropped
    "objects": 1,
    "geometries": 1,
    "geometry_types": {"mesh": 1},
    "relations": {"DISPLAY": 1, "IN_COLLECTION": 1},
    "properties": {
        "NurbsPatch": {
            "name": "NurbsPatch",
            "type": "SURFACE",
            "properties.surface_prop": "on-the-object",
            "properties.panel_id": 7.0,
        }
    },
}
