from typing import Dict, List, Set
import bpy
from bpy.types import Material, Object
from specklepy.objects.base import Base
from specklepy.objects.other import RenderMaterial
from specklepy.objects.proxies import RenderMaterialProxy
from ..utils import to_argb_int


def blender_material_to_speckle(material: Material) -> RenderMaterial:
    """
    convert a Blender material to a Speckle RenderMaterial
    """
    diffuse = -1  # default white
    opacity = 1.0
    emissive = -16777216  # default black  
    metalness = 0.0
    roughness = 1.0
    
    # extract material properties if using nodes
    if material.use_nodes and material.node_tree:
        output_node = None
        for node in material.node_tree.nodes:
            if node.type == 'OUTPUT_MATERIAL':
                output_node = node
                break
        
        # find the main shader node connected to output
        main_shader = None
        if output_node and output_node.inputs['Surface'].is_linked:
            main_shader = output_node.inputs['Surface'].links[0].from_node
        
        # handle different shader types
        # we're supporting: principled, diffuse, emmision and glass - for now
        if main_shader:
            
            if main_shader.type == 'BSDF_PRINCIPLED':
                diffuse, opacity, metalness, roughness, emissive = _extract_principled_properties(main_shader)
                
            elif main_shader.type == 'BSDF_DIFFUSE':
                color_input = main_shader.inputs.get("Color")
                if color_input:
                    if color_input.is_linked:
                        rgba = _get_color_from_connected_node(color_input.links[0].from_node)
                    else:
                        rgba = list(color_input.default_value)
                    diffuse = to_argb_int(rgba)
                roughness = 1.0 
                
            elif main_shader.type == 'EMISSION':
                color_input = main_shader.inputs.get("Color")
                strength_input = main_shader.inputs.get("Strength")
                if color_input and strength_input:
                    if color_input.is_linked:
                        rgba = _get_color_from_connected_node(color_input.links[0].from_node)
                    else:
                        rgba = list(color_input.default_value)
                    
                    strength = float(strength_input.default_value) if not strength_input.is_linked else 1.0
                    
                    if strength > 0:
                        emission_rgba = [c * strength for c in rgba[:3]] + [rgba[3]]
                        emission_rgba = [min(1.0, max(0.0, c)) for c in emission_rgba]
                        emissive = to_argb_int(emission_rgba)
                        diffuse = to_argb_int(rgba)  
                
            elif main_shader.type == 'BSDF_GLASS':
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
                opacity = 0.5  
    
    else:
        # fallback to legacy material properties
        if hasattr(material, 'diffuse_color'):
            rgba = list(material.diffuse_color) + [1.0]
            diffuse = to_argb_int(rgba)
        
        if hasattr(material, 'metallic'):
            metalness = float(material.metallic)
        
        if hasattr(material, 'roughness'):
            roughness = float(material.roughness)
    
    render_material = RenderMaterial(
        name=material.name,
        diffuse=diffuse,
        opacity=opacity,
        emissive=emissive,
        metalness=metalness,
        roughness=roughness
    )

    return render_material


def _extract_principled_properties(principled_node):
    diffuse = -1
    opacity = 1.0
    metalness = 0.0
    roughness = 1.0
    emissive = -16777216
    
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
    
    # Emission - try different possible input names for different versions
    emission_color_input = (
        principled_node.inputs.get("Emission Color") or 
        principled_node.inputs.get("Emission")
    )
    
    emission_strength_input = principled_node.inputs.get("Emission Strength")
    
    if emission_color_input:
        if emission_color_input.is_linked:
            emission_rgba = _get_color_from_connected_node(emission_color_input.links[0].from_node)
        else:
            emission_rgba = list(emission_color_input.default_value)
        
        emission_strength = 1.0 
        if emission_strength_input and not emission_strength_input.is_linked:
            emission_strength = float(emission_strength_input.default_value)
        
        if emission_strength > 0 and any(c > 0.01 for c in emission_rgba[:3]):  # Check if color is not black
            final_emission_rgba = [c * emission_strength for c in emission_rgba[:3]] + [emission_rgba[3]]
            final_emission_rgba = [min(1.0, max(0.0, c)) for c in final_emission_rgba]
            emissive = to_argb_int(final_emission_rgba)
    
    return diffuse, opacity, metalness, roughness, emissive


def _get_color_from_connected_node(node):
    if node.type == 'RGB':
        rgba = list(node.outputs['Color'].default_value)
        return rgba
    elif node.type == 'VALTORGB':  
        if node.color_ramp.elements:
            rgba = list(node.color_ramp.elements[0].color)
            return rgba
    elif hasattr(node, 'color'):
        rgba = list(node.color) + [1.0]
        return rgba
    
    # fallback to white
    return [1.0, 1.0, 1.0, 1.0]


def collect_material_assignments(objects: List[Object]) -> Dict[str, Set[str]]:

    material_assignments: Dict[str, Set[str]] = {}
    
    for obj in objects:
        if not obj or not hasattr(obj, 'data') or not obj.data:
            continue
            
        # use object name as applicationId
        application_id = obj.name
        
        # check if object has materials
        if hasattr(obj.data, 'materials') and obj.data.materials:
            for material_slot in obj.data.materials:
                if material_slot:
                    material_name = material_slot.name
                    
                    if material_name not in material_assignments:
                        material_assignments[material_name] = set()
                    
                    material_assignments[material_name].add(application_id)
    
    return material_assignments


def create_render_material_proxies(objects: List[Object]) -> List[RenderMaterialProxy]:
    material_assignments = collect_material_assignments(objects)
    
    if not material_assignments:
        return []
    
    proxies = []
    
    for material_name, object_ids in material_assignments.items():
        blender_material = bpy.data.materials.get(material_name)
        if not blender_material:
            continue
        
        speckle_material = blender_material_to_speckle(blender_material)
        
        proxy = RenderMaterialProxy(
            objects=list(object_ids),
            value=speckle_material
        )
        
        proxy.applicationId = material_name
        
        proxies.append(proxy)
    
    return proxies


def add_render_material_proxies_to_base(base: Base, objects: List[Object]) -> None:

    proxies = create_render_material_proxies(objects)
    
    if proxies:
        base.renderMaterialProxies = proxies