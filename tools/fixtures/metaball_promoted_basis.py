"""Metaball family published without its basis in the selection.

The irreducible awkwardness of metaballs, pinned as a deliberate choice. The
user selects ``Rig.001`` but not ``Rig``, and the isosurface exists only on
``Rig`` — Blender cannot polygonize a subset of a family, because the field is
summed before any surface exists.

So the connector promotes the lowest-suffix *selected* member to be the family
object, and still tessellates through the real basis. The published blob
therefore includes ``Rig``'s contribution, which the user did not select. The
alternative — publishing nothing where the viewport plainly shows a shape —
tested worse, so this is the documented behaviour, and
``_report_promoted_metaball_families`` says so on stdout rather than letting it
pass silently.

Note what is *not* here: no object for ``Rig``, and no SUBELEMENT edge. Only
selected members become objects; promotion changes which member carries the
geometry, not how wide the selection is.
"""

import bpy


def _metaball(name, location, radius=1.5):
    data = bpy.data.metaballs.new(name)
    data.resolution = 0.25
    element = data.elements.new()
    element.co = (0.0, 0.0, 0.0)
    element.radius = radius

    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    return obj


def build():
    # in the scene and contributing to the blob, but never selected
    _metaball("Rig", (0.0, 0.0, 0.0))
    member = _metaball("Rig.001", (1.5, 0.0, 0.0))

    return [member]


EXPECT = {
    # only the selected member becomes an object
    "objects": 1,
    "geometries": 1,
    "geometry_types": {"mesh": 1},
    # promoted to family object, so it carries the blob; nothing to parent
    "relations": {"DISPLAY": 1, "IN_COLLECTION": 1},
    "properties": {
        "Rig.001": {
            "type": "META",
            "properties.metaball.familyName": "Rig",
            "properties.metaball.isFamilyObject": True,
            # the family is still two members wide even though one is unselected
            "properties.metaball.memberCount": 2.0,
        }
    },
}
