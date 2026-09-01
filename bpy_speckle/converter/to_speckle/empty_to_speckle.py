"""Blender empties -> geometry-less Speckle objects.

An EMPTY has no geometry at all, so it is the one object type that publishes
with an empty ``displayValue``. It still carries meaning worth keeping: pivots,
parent nulls, and — for a collection instance — the placement itself.

The transform is published as nested scalars rather than a 16-float list because
the bundle's eav walker skips list values, so an array would silently never
reach the server. Nested dicts flatten to ``properties.transform.location.x``
and stay queryable.
"""

from typing import Any, Dict

from bpy.types import Object


def _xyz(vector, scale: float = 1.0) -> Dict[str, float]:
    return {
        "x": vector.x * scale,
        "y": vector.y * scale,
        "z": vector.z * scale,
    }


def empty_properties(
    blender_object: Object, scale_factor: float = 1.0
) -> Dict[str, Any]:
    """Transform + display settings for an empty, as flattenable scalars."""
    matrix = blender_object.matrix_world
    properties: Dict[str, Any] = {
        "transform": {
            # world-space, matching how geometry is baked elsewhere
            "location": _xyz(matrix.translation, scale_factor),
            "rotation": _xyz(matrix.to_euler()),
            "scale": _xyz(matrix.to_scale()),
        },
        "emptyDisplayType": blender_object.empty_display_type,
    }

    collection = blender_object.instance_collection
    if collection is not None:
        # a placement: the transform above is descriptive only — the authoritative
        # copy rides the InstanceProxy, pivot-corrected (see instance_unpacker)
        properties["instanceCollection"] = collection.name

    return properties
