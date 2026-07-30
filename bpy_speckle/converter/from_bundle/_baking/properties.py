"""Restore flattened bundle properties as Blender custom properties."""

from typing import Any, Dict, Optional, Tuple

import bpy

from ..bundle_reader import BundleObject
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


def _unflatten_properties(flat: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Rebuild the eav's dotted ``properties.*`` paths into a nested dict.

    The dotted path cannot be written verbatim as one custom-property key: a
    Revit parameter path blows through the 63-byte IDProperty name limit and
    aborts the bake. Nested dicts bake as IDProperty *groups* — the shape the
    classic receive produces — so only individual segments face the limit, and
    those are fitted. The eav separator is a bare ``.`` with no escaping (C#
    parity), so a key containing a literal dot nests one level deeper than
    authored; the format cannot distinguish the two.

    Returns the tree and the count of dropped paths: when a scalar and a
    subtree collide on one key, whichever arrived first stays.
    """
    tree: Dict[str, Any] = {}
    dropped = 0
    for path, value in flat.items():
        key = path[len("properties.") :]
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
    blender_object: bpy.types.Object, obj: BundleObject, result: BakeResult
) -> None:
    """Write the object's eav user properties back as Blender custom properties.

    Paths are un-flattened first (see ``_unflatten_properties``) and anything
    Blender still refuses is tallied, never raised — one bad property must not
    abort a receive whose artefacts are already downloaded and decoded.

    Only the ``properties.`` subtree round-trips — the reader routes bare root
    scalars (``type`` and any cross-producer extras) into ``root_fields``, and
    those stay internal. ``applicationId`` and ``speckle_type`` are baked
    deliberately, matching the classic receive path; the publish side's
    ``extract_custom_properties`` skips both, so they do not re-enter
    ``properties.*`` on a republish.
    """
    blender_object["applicationId"] = obj.application_id
    if obj.speckle_type:
        blender_object["speckle_type"] = obj.speckle_type
    tree, dropped = _unflatten_properties(obj.properties)
    for key, value in tree.items():
        try:
            blender_object[key] = value
        except (KeyError, TypeError, OverflowError):
            dropped += 1
    result.dropped_properties += dropped
