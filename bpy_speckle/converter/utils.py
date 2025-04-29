from typing import Tuple, List, Optional
import bpy
import mathutils
from specklepy.objects import Base
from specklepy.objects.graph_traversal.default_traversal import (
    create_default_traversal_function,
)


def to_rgba(argb_int: int) -> Tuple[float, float, float, float]:
    """
    converts the int representation of a colour into a RGBA tuple
    """
    alpha = ((argb_int >> 24) & 255) / 255
    red = ((argb_int >> 16) & 255) / 255
    green = ((argb_int >> 8) & 255) / 255
    blue = (argb_int & 255) / 255
    return (red, green, blue, alpha)


def to_argb_int(rgba_color: List[float]) -> int:
    """
    converts an RGBA array to an ARGB integer
    """
    argb_color = rgba_color[-1:] + rgba_color[:3]
    int_color = [int(val * 255) for val in argb_color]
    return int.from_bytes(int_color, byteorder="big", signed=True)


def create_material_from_proxy(
    render_material, material_name: str
) -> bpy.types.Material:
    """
    creates a Blender material from a Speckle RenderMaterial
    """
    if material_name in bpy.data.materials:
        return bpy.data.materials[material_name]

    # create new material
    material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    node_tree = material.node_tree
    nodes = node_tree.nodes

    for node in nodes:
        nodes.remove(node)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    output = nodes.new(type="ShaderNodeOutputMaterial")

    node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    if hasattr(render_material, "diffuse"):
        diffuse_rgba = to_rgba(render_material.diffuse)
        bsdf.inputs["Base Color"].default_value = (
            diffuse_rgba[0],
            diffuse_rgba[1],
            diffuse_rgba[2],
            1.0,
        )

    if hasattr(render_material, "opacity"):
        opacity = float(render_material.opacity)
        if opacity < 1.0:
            material.blend_method = "BLEND"
            bsdf.inputs["Alpha"].default_value = opacity

    if hasattr(render_material, "metalness"):
        metalness = float(render_material.metalness)
        bsdf.inputs["Metallic"].default_value = metalness

    if hasattr(render_material, "roughness"):
        roughness = float(render_material.roughness)
        bsdf.inputs["Roughness"].default_value = roughness

    if (
        hasattr(render_material, "emissive") and render_material.emissive != -16777216
    ):  # default black
        emissive_rgba = to_rgba(render_material.emissive)
        # only add emission if it's not black (default)
        if any(val > 0.01 for val in emissive_rgba[:3]):
            bsdf.inputs["Emission Color"].default_value = (
                emissive_rgba[0],
                emissive_rgba[1],
                emissive_rgba[2],
                1.0,
            )
            bsdf.inputs["Emission Strength"].default_value = 1.0

    return material


def transform_matrix(transform: List[float]) -> mathutils.Matrix:
    """
    converts a speckle transform array to a 4x4 matrix (blender needs it)
    """

    if len(transform) != 16:
        raise ValueError(f"Expected transform with 16 values, got {len(transform)}")

    return mathutils.Matrix(
        (
            (transform[0], transform[4], transform[8], transform[12]),
            (transform[1], transform[5], transform[9], transform[13]),
            (transform[2], transform[6], transform[10], transform[14]),
            (transform[3], transform[7], transform[11], transform[15]),
        )
    )


def find_object_by_id(root_object: Base, target_id: str) -> Optional[Base]:
    """
    Find an object using traversal, checking both id and applicationId
    """
    print(f"\nSearching for object with ID: {target_id}")

    traversal_function = create_default_traversal_function()

    for traversal_item in traversal_function.traverse(root_object):
        obj = traversal_item.current

        if not hasattr(obj, "id"):
            continue

        print(f"Checking object {obj.id} of type {obj.speckle_type}")

        # Check regular id
        if obj.id == target_id:
            print("Found match by id!")
            return obj

        # Check applicationId
        if hasattr(obj, "applicationId"):
            app_id = obj.applicationId
            print(f"Checking applicationId: {app_id}")
            if app_id == target_id:
                print("Found match by applicationId!")
                return obj

    print(f"Object not found with ID: {target_id}")
    return None
