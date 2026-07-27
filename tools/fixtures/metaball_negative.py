"""Metaball with a negative element: the carved blob must still have faces.

``use_negative`` subtracts an element's field instead of adding it, which is how
metaballs do boolean-style carving. The failure this guards is not a wrong
shape but an empty one: get the tessellation source wrong — pass the sibling
instead of the basis, or tessellate the un-evaluated object — and a carved
family plausibly polygonizes to zero faces, gets dropped by the empty-geometry
check, and vanishes from the publish with no error anywhere.

The negative element lives on a *sibling*, so this also covers the interesting
half of family merging: a member whose only contribution is subtractive still
belongs to the family and still publishes as a properties-only child.
"""

import bpy


def _metaball(name, location, radius, negative=False):
    data = bpy.data.metaballs.new(name)
    data.resolution = 0.2
    element = data.elements.new()
    element.co = (0.0, 0.0, 0.0)
    element.radius = radius
    element.use_negative = negative

    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build():
    solid = _metaball("Carved", (0.0, 0.0, 0.0), radius=2.5)
    # offset so it bites a chunk out rather than cancelling the blob entirely
    cutter = _metaball("Carved.001", (2.0, 0.0, 0.0), radius=1.8, negative=True)

    return [solid, cutter]


EXPECT = {
    "objects": 2,
    # the carved surface survives as one mesh; the cutter contributes no geometry
    "geometries": 1,
    "geometry_types": {"mesh": 1},
    "relations": {"DISPLAY": 1, "IN_COLLECTION": 2, "SUBELEMENT": 1},
    "subelements": {"Carved": ["Carved.001"]},
    "properties": {
        "Carved.001": {
            "type": "META",
            "properties.metaball.isFamilyObject": False,
            "properties.metaball.familyName": "Carved",
        }
    },
}
