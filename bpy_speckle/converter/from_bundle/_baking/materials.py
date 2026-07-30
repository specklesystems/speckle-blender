"""Adapt bundle material rows into Blender materials."""

from typing import Dict

import bpy

from ...utils import create_material_from_proxy
from ..bundle_reader import BundleMaterial, ReceivedBundle


class _MaterialShim:
    """Adapt a bundle material to what ``create_material_from_proxy`` expects."""

    def __init__(self, material: BundleMaterial) -> None:
        self.diffuse = material.argb
        self.opacity = material.opacity
        self.metalness = material.metalness
        self.roughness = material.roughness
        self.name = material.name


def build_materials(bundle: ReceivedBundle) -> Dict[int, bpy.types.Material]:
    """Build the node-id-to-Blender-material mapping."""
    materials: Dict[int, bpy.types.Material] = {}
    for node_id, material in bundle.materials.items():
        name = material.name or f"Material_{node_id}"
        materials[node_id] = create_material_from_proxy(_MaterialShim(material), name)
    return materials
