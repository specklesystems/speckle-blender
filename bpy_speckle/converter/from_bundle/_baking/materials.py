"""Adapt the model's material nodes into Blender materials."""

from typing import Dict

import bpy
from specklepy.bundle.bundle_reader import Node
from specklepy.bundle.model import Model

from ...utils import create_material_from_proxy


class _MaterialShim:
    """Adapt a bundle material to what ``create_material_from_proxy`` expects.

    The node's appearance columns are nullable; the defaults here are the
    spec's ("no colour" as -1, fully opaque, dielectric, matte).
    """

    def __init__(self, node: Node) -> None:
        self.diffuse = -1 if node.argb is None else node.argb
        self.opacity = 1.0 if node.opacity is None else node.opacity
        self.metalness = 0.0 if node.metalness is None else node.metalness
        self.roughness = 1.0 if node.roughness is None else node.roughness
        self.name = node.name


def build_materials(model: Model) -> Dict[int, bpy.types.Material]:
    """Build the node-k-to-Blender-material mapping."""
    materials: Dict[int, bpy.types.Material] = {}
    for material in model.materials:
        name = material.name or f"Material_{material.k}"
        # The raw node, not ``material.fields``: that raises on a NULL
        # appearance column, which would fail the whole receive.
        materials[material.k] = create_material_from_proxy(
            _MaterialShim(model.bundle.nodes[material.k]), name
        )
    return materials
