"""Adapt the model's material nodes into Blender materials."""

from typing import Dict

import bpy
from specklepy.bundle.model import Model, ModelMaterial

from ...utils import create_material_from_proxy


class _MaterialShim:
    """Adapt a bundle material to what ``create_material_from_proxy`` expects.

    The node's appearance columns are nullable; the defaults here are the
    spec's ("no colour" as -1, fully opaque, dielectric, matte).
    """

    def __init__(self, material: ModelMaterial) -> None:
        self.diffuse = -1 if material.argb is None else material.argb
        self.opacity = 1.0 if material.opacity is None else material.opacity
        self.metalness = 0.0 if material.metalness is None else material.metalness
        self.roughness = 1.0 if material.roughness is None else material.roughness
        self.name = material.name


def build_materials(model: Model) -> Dict[int, bpy.types.Material]:
    """Build the node-k-to-Blender-material mapping."""
    materials: Dict[int, bpy.types.Material] = {}
    for material in model.materials:
        name = material.name or f"Material_{material.k}"
        materials[material.k] = create_material_from_proxy(
            _MaterialShim(material), name
        )
    return materials
