"""Baseline fixture: one mesh with object-level and data-block custom properties.

Pins the property path shape reaching the eav table. Note the asymmetry this
locks in: object-level props land under ``properties.*``, while the data-block
props set here do NOT appear at all — SGEO geometry encoding drops them. That
is current intended behaviour on the bundle path, and the fixture documents it
so a change to `merge_data_block_properties()` shows up as a diff rather than a
surprise in the viewer.
"""

import bmesh
import bpy


def build():
    """Build the scene. Returns the objects to publish."""
    mesh = bpy.data.meshes.new("CubeMesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(mesh)
    bm.free()

    # data-block property — currently dropped by the bundle path
    mesh["mesh_level_prop"] = "on-the-datablock"

    obj = bpy.data.objects.new("Cube", mesh)
    obj["text_prop"] = "hello"
    obj["int_prop"] = 42
    obj["float_prop"] = 1.5
    obj["bool_prop"] = True
    bpy.context.scene.collection.objects.link(obj)

    return [obj]


EXPECT = {
    "objects": 1,
    "geometries": 1,
    "geometry_types": {"mesh": 1},
    "collections": ["Untitled.blend"],
    "relations": {"DISPLAY": 1, "IN_COLLECTION": 1},
    "scene_views": ["Collections"],
    "properties": {
        "Cube": {
            "name": "Cube",
            "type": "MESH",
            "properties.text_prop": "hello",
            "properties.int_prop": 42.0,
            "properties.float_prop": 1.5,
        }
    },
}
