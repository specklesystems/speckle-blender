"""Metaball baseline: one lone metaball publishes as an ordinary mesh.

The simplest META case, and the one that must not regress into cleverness. A
metaball with no same-named siblings is its own family basis, so it carries the
blob itself and emits no SUBELEMENT edges at all — the parent/child machinery
stays entirely out of the way.

Also pins that the isosurface reaches the bundle in *world* coordinates: the
object sits at x=5, so a mesh baked in local space would be caught by the
translation showing up in the geometry rather than the transform.
"""

import bpy


def build():
    metaball = bpy.data.metaballs.new("Blob")
    metaball.resolution = 0.25
    element = metaball.elements.new()
    element.co = (0.0, 0.0, 0.0)
    element.radius = 2.0

    obj = bpy.data.objects.new("Blob", metaball)
    obj.location = (5.0, 0.0, 0.0)
    obj["blob_prop"] = "on-the-object"
    bpy.context.scene.collection.objects.link(obj)

    return [obj]


EXPECT = {
    "objects": 1,
    "geometries": 1,
    "geometry_types": {"mesh": 1},
    # no siblings, so no parent/child layer
    "relations": {"DISPLAY": 1, "IN_COLLECTION": 1},
    "properties": {
        "Blob": {
            "name": "Blob",
            "type": "META",
            "properties.blob_prop": "on-the-object",
            "properties.metaball.familyName": "Blob",
            "properties.metaball.isFamilyObject": True,
            "properties.metaball.memberCount": 1.0,
            "properties.metaball.elementCount": 1.0,
            "properties.metaball.elementTypes.BALL": 1.0,
            # world transform, not the stale identity of an un-updated depsgraph
            "properties.metaball.location.x": 5.0,
            # viewport resolution, deliberately — not render_resolution
            "properties.metaball.resolution": 0.25,
        }
    },
}
