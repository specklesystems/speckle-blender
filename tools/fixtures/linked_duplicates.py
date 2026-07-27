"""Linked-duplicate fixture: two objects per data-block, at different transforms.

Guards the geometry-id keying. displayValue geometry is baked into world
coordinates, so linked duplicates share a data-block but describe *different*
geometry. When the geometry applicationId was keyed on the data-block, both
duplicates produced the same id, the bundle exporter's id-keyed cache wrote only
the first one, and every duplicate rendered stacked at the first one's transform.

The tell is a count: N duplicates must yield N geometries, not one. In the viewer
this regression is nearly invisible — a cube is at *a* plausible place, just not
its own — so the count is the only reliable check. Covers both id helpers: meshes
(``get_submesh_id``) and wire-curve splines (``get_curve_element_id``).
"""

import bmesh
import bpy


def _linked_cubes():
    mesh = bpy.data.meshes.new("SharedCubeMesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()

    objects = []
    for name, x in (("CubeAtOrigin", 0.0), ("CubeFarAway", 10.0)):
        obj = bpy.data.objects.new(name, mesh)  # same data-block, both objects
        obj.location = (x, 0.0, 0.0)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
    return objects


def _linked_wires():
    curve = bpy.data.curves.new("SharedWireCurve", type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(1)
    for i, point in enumerate(spline.bezier_points):
        point.co = (float(i), 0.0, 0.0)
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"

    objects = []
    for name, y in (("WireAtOrigin", 0.0), ("WireFarAway", 10.0)):
        obj = bpy.data.objects.new(name, curve)
        obj.location = (0.0, y, 0.0)
        bpy.context.scene.collection.objects.link(obj)
        objects.append(obj)
    return objects


def build():
    objects = _linked_cubes() + _linked_wires()
    # matrix_world is derived lazily from location — without this the conversion
    # reads identity matrices and every copy bakes to the origin anyway, which
    # would make this fixture pass for the wrong reason.
    bpy.context.view_layer.update()
    return objects


EXPECT = {
    "objects": 4,
    # the assertion that matters: one geometry per OBJECT, not per data-block.
    # With data-block keying this was 2 (one cube, one wire) and the far copies
    # silently reused the geometry baked at the origin.
    "geometries": 4,
    "geometry_types": {"mesh": 2, "curve": 2},
    "relations": {"DISPLAY": 4, "IN_COLLECTION": 4},
    "properties": {
        "CubeAtOrigin": {"name": "CubeAtOrigin", "type": "MESH"},
        "CubeFarAway": {"name": "CubeFarAway", "type": "MESH"},
        "WireAtOrigin": {"name": "WireAtOrigin", "type": "CURVE"},
        "WireFarAway": {"name": "WireFarAway", "type": "CURVE"},
    },
}
