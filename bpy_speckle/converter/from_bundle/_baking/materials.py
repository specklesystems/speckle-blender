"""Adapt the model's material nodes into Blender materials."""

from typing import Dict

import bpy
from specklepy.bundle.model import Model, ModelMaterial

from ...utils import create_material_from_proxy


class _MaterialShim:
    """Adapt a bundle material to what ``create_material_from_proxy`` expects."""

    def __init__(self, material: ModelMaterial) -> None:
        fields = material.fields
        self.diffuse = fields.argb
        self.opacity = fields.opacity
        self.metalness = fields.metalness
        self.roughness = fields.roughness
        self.name = fields.name


def build_materials(model: Model) -> Dict[int, bpy.types.Material]:
    """Build the node-k-to-Blender-material mapping."""
    materials: Dict[int, bpy.types.Material] = {}
    for material in model.materials:
        name = material.name or f"Material_{material.k}"
        materials[material.k] = create_material_from_proxy(
            _MaterialShim(material), name
        )
    return materials
