from bpy.types import Object
from typing import Optional
from specklepy.objects.data_objects import BlenderObject
from .curve_to_speckle import curve_to_speckle
from .mesh_to_speckle import mesh_to_speckle_meshes
from .utils import get_object_id, get_curve_element_id


def convert_to_speckle(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> Optional[BlenderObject]:
    display_value = []
    properties = {}

    if blender_object.type == "CURVE":
        # handle curve modifiers apply_modifiers is True
        if apply_modifiers and blender_object.modifiers:
            import bpy
            
            # Convert curve with modifiers to mesh
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = blender_object.evaluated_get(depsgraph)
            evaluated_mesh = evaluated_obj.to_mesh()
            
            if evaluated_mesh:
                meshes = mesh_to_speckle_meshes(
                    blender_object, evaluated_mesh, scale_factor, units
                )
                blender_object.to_mesh_clear()
                if meshes:
                    display_value = meshes
        else:
            # curve conversion without modifiers
            curve_result = curve_to_speckle(blender_object, scale_factor)
            if curve_result and hasattr(curve_result, "@elements"):
                display_value = curve_result["@elements"]
                for i, element in enumerate(display_value):
                    if hasattr(element, "applicationId"):
                        element.applicationId = get_curve_element_id(blender_object, i)
            elif curve_result:
                if hasattr(curve_result, "applicationId"):
                    curve_result.applicationId = get_curve_element_id(blender_object, 0)
                display_value = [curve_result]

    elif blender_object.type == "MESH":
        # get mesh data - apply modifiers if requested
        mesh_data = blender_object.data
        if apply_modifiers and blender_object.modifiers:
            import bpy
            
            # use evaluated object to get mesh with modifiers applied
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = blender_object.evaluated_get(depsgraph)
            evaluated_mesh = evaluated_obj.to_mesh()
            mesh_data = evaluated_mesh
        
        meshes = mesh_to_speckle_meshes(
            blender_object, mesh_data, scale_factor, units
        )
        
        if apply_modifiers and blender_object.modifiers and mesh_data != blender_object.data:
            blender_object.to_mesh_clear()
        
        if meshes:
            display_value = meshes

    if not display_value:
        return None

    if not isinstance(display_value, list):
        display_value = [display_value]

    return BlenderObject(
        name=blender_object.name,
        type=blender_object.type,
        displayValue=display_value,
        applicationId=get_object_id(blender_object),
        properties=properties,
        units=units,
    )
