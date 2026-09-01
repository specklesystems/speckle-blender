"""Restore flattened bundle properties as Blender custom properties."""

from typing import Any, Dict, Iterable, Optional, Tuple

import bpy
from specklepy.bundle.model import ModelObject

from .result import BakeResult

# IDProperty names live in a fixed 64-byte buffer (63 + NUL) at every level of
# a property group; Blender raises rather than truncating.
_MAX_IDPROP_NAME_BYTES = 63


def _fit_idprop_name(segment: str) -> str:
    """Trim a path segment to Blender's IDProperty name limit.

    The limit is bytes, not characters, so the cut lands on a UTF-8 boundary —
    a multi-byte parameter name hits the wall sooner than its length suggests.
    """
    encoded = segment.encode("utf-8")
    if len(encoded) <= _MAX_IDPROP_NAME_BYTES:
        return segment
    return encoded[:_MAX_IDPROP_NAME_BYTES].decode("utf-8", errors="ignore")


def _unflatten_properties(
    flat: Iterable[Tuple[str, Any]],
) -> Tuple[Dict[str, Any], int]:
    """Rebuild dotted property paths into a nested dict.

    ``flat`` is the ``properties.``-stripped key/value view of one object's eav
    rows (``ModelObject.properties``). The dotted path cannot be written
    verbatim as one custom-property key: a Revit parameter path blows through
    the 63-byte IDProperty name limit and aborts the bake. Nested dicts bake as
    IDProperty *groups*, so only individual segments face the limit, and those
    are fitted. The eav separator is a bare ``.`` with no escaping (C# parity),
    so a key containing a literal dot nests one level deeper than authored; the
    format cannot distinguish the two.

    Returns the tree and the count of dropped paths: when a scalar and a
    subtree collide on one key, whichever arrived first stays.
    """
    tree: Dict[str, Any] = {}
    dropped = 0
    for key, value in flat:
        if not key or value is None:
            continue
        segments = [_fit_idprop_name(s) for s in key.split(".") if s]
        if not segments:
            continue
        node: Optional[Dict[str, Any]] = tree
        for segment in segments[:-1]:
            child = node.setdefault(segment, {})
            if not isinstance(child, dict):
                node = None
                break
            node = child
        if node is None or isinstance(node.get(segments[-1]), dict):
            dropped += 1
            continue
        node[segments[-1]] = value
    return tree, dropped


def apply_properties(
    blender_object: bpy.types.Object, obj: ModelObject, result: BakeResult
) -> None:
    """Write the object's eav user properties back as Blender custom properties.

    Paths are un-flattened first (see ``_unflatten_properties``) and anything
    Blender still refuses is tallied, never raised — one bad property must not
    abort a receive whose artefacts are already downloaded and decoded.

    Only the ``properties.`` subtree round-trips — bare root scalars (``type``,
    ``units`` and any cross-producer extras) stay internal schema state.
    ``applicationId`` and ``speckle_type`` are baked deliberately; the publish
    side's ``extract_custom_properties`` skips both, so they do not re-enter
    ``properties.*`` on a republish.
    """
    blender_object["applicationId"] = obj.application_id
    speckle_type = obj.root_properties.get_string("speckle_type")
    if speckle_type:
        blender_object["speckle_type"] = speckle_type
    tree, dropped = _unflatten_properties(obj.properties.items())
    for key, value in tree.items():
        try:
            blender_object[key] = value
        except (KeyError, TypeError, OverflowError):
            dropped += 1
    result.dropped_properties += dropped
