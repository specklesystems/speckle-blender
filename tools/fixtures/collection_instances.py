"""Collection-instance fixture: placements, pivots, and member suppression.

Before this was implemented an instancing EMPTY converted to nothing and was
dropped silently, so a scene built from collection instances published as an
empty version. Now a placement becomes an INSTANCE node (transform) pointing at
a DEFINITION node (the instanced collection), and the definition's members ship
once in definition-local coordinates.

Two things this pins that are easy to get wrong:

- **The pivot.** Blender bakes ``collection.instance_offset`` into where an empty
  draws its contents, so it has to come back out of the placement transform.
  ``Widget`` has a non-zero offset and ``Gadget`` does not, so a dropped (or
  double-applied) offset moves one set of placements and not the other.
- **Selection-aware suppression.** ``WidgetCube`` is pulled in behind its
  placements and renders only through them: no IN_COLLECTION, no DISPLAY.
  ``GadgetCube`` is in the publish selection in its own right, so it stays a real
  scene object *and* is referenced by its definition. Getting this wrong is
  invisible in a count of objects — it shows up as a duplicate at the origin.
"""

import bmesh
import bpy


def _cube(name, location=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    return obj


def _definition(name, offset=(0.0, 0.0, 0.0)):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    collection.instance_offset = offset
    return collection


def _placement(name, collection, location):
    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = collection
    empty.location = location
    bpy.context.scene.collection.objects.link(empty)
    return empty


def build():
    # a definition with a pivot offset, placed twice
    widget = _definition("Widget", offset=(1.0, 0.0, 0.0))
    widget_cube = _cube("WidgetCube")
    # a definition-only member is never in the caller's selection, so its material
    # only survives if the proxies are built from the *expanded* object list
    widget_cube.data.materials.append(bpy.data.materials.new("WidgetPaint"))
    widget.objects.link(widget_cube)

    # a definition with no offset, whose member is also published standalone
    gadget = _definition("Gadget")
    gadget_cube = _cube("GadgetCube")
    gadget.objects.link(gadget_cube)

    placements = [
        _placement("PlacementA", widget, (10.0, 0.0, 0.0)),
        _placement("PlacementB", widget, (0.0, 20.0, 0.0)),
        _placement("PlacementC", gadget, (0.0, 0.0, 30.0)),
    ]

    bpy.context.view_layer.update()

    # WidgetCube is deliberately absent: it reaches the bundle only because a
    # placement needs it, which is what makes it definition-only
    return placements + [gadget_cube]


EXPECT = {
    # 3 placements + both members (pulled in / selected)
    "objects": 5,
    # one per member, in definition-local coordinates — NOT one per placement
    "geometries": 2,
    "geometry_types": {"mesh": 2},
    # Widget holds nothing but a definition-only member, so it contributes no
    # IN_COLLECTION edge and must NOT surface as an empty folder in the scene
    # tree; it exists as a DEFINITION node instead. Gadget still holds a real
    # standalone object, so it stays.
    "collections": ["Untitled.blend", "Gadget"],
    "definitions": ["Widget", "Gadget"],
    "definition_members": {"Widget": 1, "Gadget": 1},
    "instances": 3,
    "instance_definitions": {
        "PlacementA": "Widget",
        "PlacementB": "Widget",
        "PlacementC": "Gadget",
    },
    # empty.matrix_world @ Translation(-instance_offset): Widget's pivot shifts
    # its placements by -1 in x, Gadget's placement is untouched
    "instance_translations": {
        "PlacementA": [9.0, 0.0, 0.0],
        "PlacementB": [-1.0, 20.0, 0.0],
        "PlacementC": [0.0, 0.0, 30.0],
    },
    # the member's material rides its geometry even though the member itself is
    # never in the publish selection
    "material_names": ["WidgetPaint"],
    "relations": {
        "HAS_MATERIAL": 1,
        "DISPLAY_INSTANCE": 3,
        "DEFINES": 2,
        # only GadgetCube draws directly; WidgetCube renders through placements
        "DISPLAY": 1,
        # the 3 placements + GadgetCube standing on its own
        "IN_COLLECTION": 4,
    },
    "object_collections": {
        "PlacementA": "Untitled.blend",
        "PlacementB": "Untitled.blend",
        "PlacementC": "Untitled.blend",
        "GadgetCube": "Gadget",
    },
}
