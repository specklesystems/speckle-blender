"""The public outcome and diagnostics of a bundle bake."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import bpy


@dataclass
class BakeResult:
    """What a bake produced, and what it could not."""

    objects: Dict[str, object] = field(default_factory=dict)
    root_collection: Optional[bpy.types.Collection] = None
    # geometry type -> how many blobs were skipped for want of a decoder. An
    # object whose geometry is *entirely* undecodable is dropped outright.
    skipped_by_type: Dict[str, int] = field(default_factory=dict)
    # (application_id, reason) for geometry that failed to decode
    decode_errors: List[Tuple[str, str]] = field(default_factory=list)
    # container subtype -> how many CONTAINERs had no Blender mapping. Surfaced
    # instead of baking them as misleading empty collections.
    unmapped_containers: Dict[str, int] = field(default_factory=dict)
    # eav property paths that could not be stored as custom properties —
    # scalar/subtree collisions after un-flattening, or a value Blender refused.
    dropped_properties: int = 0

    @property
    def skipped_count(self) -> int:
        return sum(self.skipped_by_type.values())
