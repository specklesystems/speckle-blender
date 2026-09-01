"""Nested collection instances: a definition that itself contains a placement.

``Branch`` contains nothing but an empty that places ``Leaf``, and the scene
places ``Branch`` once. That makes the inner empty two things at once — a
placement (INSTANCE node) and a member of an enclosing definition — which is the
only way DEFINES_INSTANCE gets emitted.

The failure this guards is quiet: if a nested placement is treated as an ordinary
top-level one, it keeps a DISPLAY_INSTANCE of its own and the leaf geometry draws
twice, once through the outer placement and once at the inner empty's authored
location.
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


def _collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def _placement(name, collection, location):
    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = collection
    empty.location = location
    return empty


def build():
    leaf = _collection("Leaf")
    leaf.objects.link(_cube("LeafCube"))

    # the inner placement lives inside Branch, so it is a definition member
    branch = _collection("Branch")
    branch.objects.link(_placement("InnerPlacement", leaf, (5.0, 0.0, 0.0)))

    outer = _placement("OuterPlacement", branch, (0.0, 100.0, 0.0))
    bpy.context.scene.collection.objects.link(outer)

    bpy.context.view_layer.update()

    # only the outer placement is published; everything else is reached through it
    return [outer]


EXPECT = {
    # OuterPlacement + InnerPlacement + LeafCube
    "objects": 3,
    "geometries": 1,
    # both Leaf and Branch exist only to be instanced, so neither leaves an empty
    # folder behind in the scene tree — only the root survives
    "collections": ["Untitled.blend"],
    "definitions": ["Branch", "Leaf"],
    # Branch owns the inner placement; Leaf owns the cube
    "definition_members": {"Branch": 1, "Leaf": 1},
    "instances": 2,
    # only the outer placement is reached from an object — the inner one is
    # reached from its definition instead
    "instance_definitions": {"OuterPlacement": "Branch"},
    "instance_translations": {"OuterPlacement": [0.0, 100.0, 0.0]},
    "relations": {
        "DISPLAY_INSTANCE": 1,
        "DEFINES_INSTANCE": 1,
        # the builder's nested-member shape also records which object the
        # placement represents (DEFINES_MEMBER) and what it places (PLACES),
        # matching the C# connectors
        "DEFINES_MEMBER": 1,
        "PLACES": 1,
        "DEFINES": 1,
        "DISPLAY": 0,
        "IN_COLLECTION": 1,
    },
    "object_collections": {"OuterPlacement": "Untitled.blend"},
}

# Round-trip (ENG-9025): LINKED_DUPLICATES must hold recursively. The nested
# placement inside Branch may not survive as a COLLECTION-instance empty in the
# copies — it is rebuilt as a plain empty (Leaf.002) whose child is a real copy
# of the leaf cube (Leaf.003), and the transform parent-chains: outer placement
# at y=100 composed with the inner one at x=5 puts both at (5, 100, 0).
#
# InnerPlacement and LeafCube as shapeless empties at the origin are the same
# pre-existing properties-row wart pinned in collection_instances.
EXPECT_RECEIVE = {
    "INSTANCE_PROXIES": {
        "collections": ["Received", "Scene Collection"],
        "object_collections": {
            "InnerPlacement": ["Received"],
            "LeafCube": ["Received"],
            "OuterPlacement": ["Received"],
        },
        "collection_instances": ["OuterPlacement"],
        "translations": {"OuterPlacement": [0.0, 100.0, 0.0]},
    },
    "LINKED_DUPLICATES": {
        "collections": ["Received", "Scene Collection"],
        "object_collections": {
            "InnerPlacement": ["Received"],
            "Leaf.002": ["Received"],
            "Leaf.003": ["Received"],
            "LeafCube": ["Received"],
            "OuterPlacement": ["Received"],
        },
        "collection_instances": [],
        "parents": {
            "Leaf.002": "OuterPlacement",
            "Leaf.003": "Leaf.002",
        },
        "translations": {
            "Leaf.002": [5.0, 100.0, 0.0],
            "Leaf.003": [5.0, 100.0, 0.0],
        },
    },
}
