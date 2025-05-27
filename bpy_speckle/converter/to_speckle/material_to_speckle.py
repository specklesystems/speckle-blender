"""
Functions for converting Blender materials to Speckle RenderMaterial and RenderMaterialProxy objects.
"""

from typing import Dict, List, Set
import bpy
from bpy.types import Material, Object
from specklepy.objects.base import Base
from specklepy.objects.other import RenderMaterial
from specklepy.objects.proxies import RenderMaterialProxy
from ..utils import to_argb_int


def blender_material_to_speckle(material: Material) -> RenderMaterial:
    """
    Convert a Blender material to a Speckle RenderMaterial.
    
    Args:
        material: The Blender material to convert
        
    Returns:
        A Speckle RenderMaterial object
    """
    # Default values
    diffuse = -1  # Default white
    opacity = 1.0
    emissive = -16777216  # Default black  
    metalness = 0.0
    roughness = 1.0
    
    # Extract material properties if using nodes
    if material.use_nodes and material.node_tree:
        # Find the output node to trace back from
        output_node = None
        for node in material.node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break
        
        # Find the main shader node connected to output
        main_shader = None
        if output_node and output_node.inputs['Surface'].is_linked:
            main_shader = output_node.inputs['Surface'].links[0].from_node
        
        if main_shader:
            # Handle different shader types
            if main_shader.type == 'BSDF_PRINCIPLED':
                # Principled BSDF
                diffuse, opacity, metalness, roughness, emissive = _extract_principled_properties(main_shader)
                
            elif main_shader.type == 'BSDF_DIFFUSE':
                # Diffuse BSDF
                color_input = main_shader.inputs.get("Color")
                if color_input:
                    if color_input.is_linked:
                        # Try to get color from connected node
                        rgba = _get_color_from_connected_node(color_input.links[0].from_node)
                    else:
                        rgba = list(color_input.default_value)
                    diffuse = to_argb_int(rgba)
                roughness = 1.0  # Diffuse is fully rough
                
            elif main_shader.type == 'EMISSION':
                # Emission Shader
                color_input = main_shader.inputs.get("Color")
                strength_input = main_shader.inputs.get("Strength")
                if color_input and strength_input:
                    if color_input.is_linked:
                        rgba = _get_color_from_connected_node(color_input.links[0].from_node)
                    else:
                        rgba = list(color_input.default_value)
                    
                    strength = float(strength_input.default_value) if not strength_input.is_linked else 1.0
                    
                    # Apply emission strength
                    if strength > 0:
                        emission_rgba = [c * strength for c in rgba[:3]] + [rgba[3]]
                        emission_rgba = [min(1.0, max(0.0, c)) for c in emission_rgba]
                        emissive = to_argb_int(emission_rgba)
                        diffuse = to_argb_int(rgba)  # Also set diffuse for visibility
                
            elif main_shader.type == 'BSDF_GLASS':
                # Glass BSDF
                color_input = main_shader.inputs.get("Color")
                if color_input:
                    if color_input.is_linked:
                        rgba = _get_color_from_connected_node(color_input.links[0].from_node)
                    else:
                        rgba = list(color_input.default_value)
                    diffuse = to_argb_int(rgba)
                roughness_input = main_shader.inputs.get("Roughness")
                if roughness_input:
                    roughness = float(roughness_input.default_value) if not roughness_input.is_linked else 0.0
                opacity = 0.5  # Glass is typically semi-transparent
    
    else:
        # Fallback to legacy material properties
        if hasattr(material, 'diffuse_color'):
            rgba = list(material.diffuse_color) + [1.0]  # Add alpha
            diffuse = to_argb_int(rgba)
        
        if hasattr(material, 'metallic'):
            metalness = float(material.metallic)
        
        if hasattr(material, 'roughness'):
            roughness = float(material.roughness)
    
    # Create the RenderMaterial
    render_material = RenderMaterial(
        name=material.name,
        diffuse=diffuse,
        opacity=opacity,
        emissive=emissive,
        metalness=metalness,
        roughness=roughness
    )
    
    # Debug: Print all material values
    print(f"Final RenderMaterial '{material.name}': diffuse={diffuse}, emissive={emissive}")
    
    return render_material


def _extract_principled_properties(principled_node):
    """Extract properties from a Principled BSDF node."""
    diffuse = -1
    opacity = 1.0
    metalness = 0.0
    roughness = 1.0
    emissive = -16777216
    
    # Base Color (Diffuse)
    base_color_input = principled_node.inputs.get("Base Color")
    if base_color_input:
        if base_color_input.is_linked:
            rgba = _get_color_from_connected_node(base_color_input.links[0].from_node)
        else:
            rgba = list(base_color_input.default_value)
        diffuse = to_argb_int(rgba)
    
    # Alpha/Opacity
    alpha_input = principled_node.inputs.get("Alpha")
    if alpha_input and not alpha_input.is_linked:
        opacity = float(alpha_input.default_value)
    
    # Metallic
    metallic_input = principled_node.inputs.get("Metallic")
    if metallic_input and not metallic_input.is_linked:
        metalness = float(metallic_input.default_value)
    
    # Roughness
    roughness_input = principled_node.inputs.get("Roughness")
    if roughness_input and not roughness_input.is_linked:
        roughness = float(roughness_input.default_value)
    
    # Emission - try different possible input names
    emission_color_input = (
        principled_node.inputs.get("Emission Color") or 
        principled_node.inputs.get("Emission")
    )
    
    emission_strength_input = principled_node.inputs.get("Emission Strength")
    
    if emission_color_input:
        # Get emission color
        if emission_color_input.is_linked:
            emission_rgba = _get_color_from_connected_node(emission_color_input.links[0].from_node)
        else:
            emission_rgba = list(emission_color_input.default_value)
        
        # Get emission strength
        emission_strength = 1.0  # Default strength
        if emission_strength_input and not emission_strength_input.is_linked:
            emission_strength = float(emission_strength_input.default_value)
        
        # Apply emission strength to color and check if it's actually emissive
        if emission_strength > 0 and any(c > 0.01 for c in emission_rgba[:3]):  # Check if color is not black
            # Apply strength to RGB channels
            final_emission_rgba = [c * emission_strength for c in emission_rgba[:3]] + [emission_rgba[3]]
            # Clamp values to [0, 1]
            final_emission_rgba = [min(1.0, max(0.0, c)) for c in final_emission_rgba]
            emissive = to_argb_int(final_emission_rgba)
    
    return diffuse, opacity, metalness, roughness, emissive


def _get_color_from_connected_node(node):
    """Try to extract color from a connected node (like ColorRamp, RGB, etc.)."""
    if node.type == 'RGB':
        # RGB node
        rgba = list(node.outputs['Color'].default_value)
        return rgba
    elif node.type == 'VALTORGB':  # ColorRamp
        # Use the first color stop as approximation
        if node.color_ramp.elements:
            rgba = list(node.color_ramp.elements[0].color)
            return rgba
    elif hasattr(node, 'color'):
        # Some nodes have a color property
        rgba = list(node.color) + [1.0]
        return rgba
    
    # Fallback to white
    return [1.0, 1.0, 1.0, 1.0]


def collect_material_assignments(objects: List[Object]) -> Dict[str, Set[str]]:
    """
    Collect material assignments from objects.
    
    Args:
        objects: List of Blender objects to analyze
        
    Returns:
        Dictionary mapping material names to sets of object applicationIds
    """
    material_assignments: Dict[str, Set[str]] = {}
    
    for obj in objects:
        if not obj or not hasattr(obj, 'data') or not obj.data:
            continue
            
        # Use object name as applicationId (consistent with to_speckle.py)
        application_id = obj.name
        
        # Check if object has materials
        if hasattr(obj.data, 'materials') and obj.data.materials:
            for material_slot in obj.data.materials:
                if material_slot:  # Material slot is not empty
                    material_name = material_slot.name
                    
                    if material_name not in material_assignments:
                        material_assignments[material_name] = set()
                    
                    material_assignments[material_name].add(application_id)
    
    return material_assignments


def create_render_material_proxies(objects: List[Object]) -> List[RenderMaterialProxy]:
    """
    Create RenderMaterialProxy objects for the given objects.
    
    Args:
        objects: List of Blender objects to process
        
    Returns:
        List of RenderMaterialProxy objects
    """
    # Collect material assignments
    material_assignments = collect_material_assignments(objects)
    
    if not material_assignments:
        return []
    
    proxies = []
    
    for material_name, object_ids in material_assignments.items():
        # Get the Blender material
        blender_material = bpy.data.materials.get(material_name)
        if not blender_material:
            continue
        
        # Convert to Speckle RenderMaterial
        speckle_material = blender_material_to_speckle(blender_material)
        
        # Create the proxy
        proxy = RenderMaterialProxy(
            objects=list(object_ids),
            value=speckle_material
        )
        
        # Set applicationId to material name for consistency
        proxy.applicationId = material_name
        
        proxies.append(proxy)
    
    return proxies


def add_render_material_proxies_to_base(base: Base, objects: List[Object]) -> None:
    """
    Add render material proxies to a base object.
    
    Args:
        base: The base object to add proxies to
        objects: List of Blender objects to process materials from
    """
    proxies = create_render_material_proxies(objects)
    
    if proxies:
        base.renderMaterialProxies = proxies