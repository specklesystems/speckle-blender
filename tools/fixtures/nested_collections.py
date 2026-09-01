"""Collection hierarchy fixture: two levels of nesting plus a root-level object.

Exercises the part of ``build_collection_hierarchy`` that is easiest to break
silently — ``find_target_collection_for_object`` picks the *deepest* collection
containing an object, and objects with no collection fall back to the root. In
the viewer a misplaced object still renders correctly, so hierarchy regressions
are almost invisible there; here they are a count mismatch.
"""

import bmesh
import bpy


def _cube(name):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    return bpy.data.objects.new(name, mesh)


def build():
    scene_root = bpy.context.scene.collection

    outer = bpy.data.collections.new("Outer")
    scene_root.children.link(outer)
    inner = bpy.data.collections.new("Inner")
    outer.children.link(inner)

    at_root = _cube("AtRoot")
    scene_root.objects.link(at_root)

    in_outer = _cube("InOuter")
    outer.objects.link(in_outer)

    in_inner = _cube("InInner")
    inner.objects.link(in_inner)

    return [at_root, in_outer, in_inner]


EXPECT = {
    "objects": 3,
    "geometries": 3,
    "geometry_types": {"mesh": 3},
    # the Blender scene collection becomes the bundle root, named for the file
    "collections": ["Untitled.blend", "Outer", "Inner"],
    # parentage rides on the node's def_ref, not on an IN_COLLECTION relation
    "collection_parents": {
        "Untitled.blend": None,
        "Outer": "Untitled.blend",
        "Inner": "Outer",
    },
    # the assertion that actually matters: each object in its *deepest* collection
    "object_collections": {
        "AtRoot": "Untitled.blend",
        "InOuter": "Outer",
        "InInner": "Inner",
    },
    "relations": {"DISPLAY": 3, "IN_COLLECTION": 3},
    "properties": {
        "AtRoot": {"name": "AtRoot"},
        "InOuter": {"name": "InOuter"},
        "InInner": {"name": "InInner"},
    },
}
