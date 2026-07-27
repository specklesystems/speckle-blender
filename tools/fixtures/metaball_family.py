"""Metaball family: three members, one blob, two SUBELEMENT children.

The case the whole feature exists for. ``Mball``, ``Mball.001`` and
``Mball.007`` share a base name, so Blender sums their fields and polygonizes
one merged isosurface onto the basis. The connector publishes that as:

- one geometry, on the basis — *not* three, and not one per member
- two SUBELEMENT edges, basis -> sibling, in numeric-suffix order
- three IN_COLLECTION edges: every member stays a real object in the tree, so
  it keeps its own properties and remains selectable in the viewer

The two siblings carry no DISPLAY edge, which is the assertion that catches the
tempting bug: giving each member the family blob, so the same surface renders
three times stacked on itself.

A second, unrelated ``Solo`` metaball guards against over-grouping — a family
key is the base name, so a differently named metaball must stay independent.
"""

import bpy


def _metaball(name, location, radius=1.5):
    data = bpy.data.metaballs.new(name)
    data.resolution = 0.3
    element = data.elements.new()
    element.co = (0.0, 0.0, 0.0)
    element.radius = radius

    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build():
    # deliberately linked out of suffix order: ordering must come from the name,
    # not from selection or scene order
    seven = _metaball("Mball.007", (3.0, 0.0, 0.0))
    basis = _metaball("Mball", (0.0, 0.0, 0.0))
    one = _metaball("Mball.001", (1.5, 0.0, 0.0))

    basis["family_prop"] = "on-the-basis"
    one["member_prop"] = "on-the-member"

    solo = _metaball("Solo", (20.0, 0.0, 0.0))

    return [seven, basis, one, solo]


EXPECT = {
    # 3 family members + Solo; only 2 of them own geometry
    "objects": 4,
    "geometries": 2,
    "geometry_types": {"mesh": 2},
    "relations": {
        # the family basis and Solo, not the two siblings
        "DISPLAY": 2,
        # every member keeps its place in the collection tree
        "IN_COLLECTION": 4,
        "SUBELEMENT": 2,
    },
    "subelements": {"Mball": ["Mball.001", "Mball.007"]},
    "properties": {
        "Mball": {
            "type": "META",
            "properties.family_prop": "on-the-basis",
            "properties.metaball.familyName": "Mball",
            "properties.metaball.isFamilyObject": True,
            # counts the whole family, including members the blob merged in
            "properties.metaball.memberCount": 3.0,
        },
        "Mball.001": {
            "type": "META",
            "properties.member_prop": "on-the-member",
            "properties.metaball.familyName": "Mball",
            "properties.metaball.isFamilyObject": False,
            # a child has no geometry, so its location is the only record of
            # where it pulled the blob
            "properties.metaball.location.x": 1.5,
        },
        "Solo": {
            "properties.metaball.familyName": "Solo",
            "properties.metaball.isFamilyObject": True,
            "properties.metaball.memberCount": 1.0,
        },
    },
}
