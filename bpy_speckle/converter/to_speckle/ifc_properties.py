from typing import Dict, Any
from bpy.types import Object


def extract_ifc_properties(blender_object: Object) -> Dict[str, Any]:
    """
    Extract IFC properties from a Blender object if it has IFC data.
    """
    try:
        import bonsai.tool as tool

        # Check if object has IFC data
        if not hasattr(blender_object, "BIMObjectProperties"):
            return {}

        if not blender_object.BIMObjectProperties.ifc_definition_id:
            return {}

        # Check if IFC file is loaded
        if not tool.Ifc.get():
            return {}

        # Get IFC entity
        ifc_entity = tool.Ifc.get_entity(blender_object)
        if not ifc_entity:
            return {}

        # Initialize result dictionary
        ifc_properties = {}

        # Extract IFC attributes
        ifc_properties["ifc_attributes"] = _extract_ifc_attributes(ifc_entity)

        # Extract property sets
        ifc_properties["ifc_property_sets"] = _extract_property_sets(ifc_entity)

        # Extract type information
        ifc_properties["ifc_type_info"] = _extract_type_info(ifc_entity)

        # Extract spatial information
        ifc_properties["ifc_spatial_info"] = _extract_spatial_info(ifc_entity)

        # Extract material information
        ifc_properties["ifc_materials"] = _extract_material_info(ifc_entity)

        # Remove empty sections to keep output clean
        ifc_properties = {k: v for k, v in ifc_properties.items() if v}

        return ifc_properties

    except ImportError:
        # Bonsai/ifcopenshell not available, silently return empty dict
        return {}
    except Exception as e:
        # Other errors, log and return empty dict
        print(f"Error extracting IFC properties: {e}")
        return {}


def _extract_ifc_attributes(ifc_entity) -> Dict[str, Any]:
    """Extract basic IFC attributes from an entity."""
    try:
        attributes = {}

        # Get all attributes
        entity_info = ifc_entity.get_info()

        # Filter out None values and complex types
        for attr_name, attr_value in entity_info.items():
            if attr_value is not None and not hasattr(attr_value, "is_a"):
                # Only include simple types that can be serialized
                if isinstance(attr_value, (str, int, float, bool)):
                    attributes[attr_name] = attr_value
                elif isinstance(attr_value, (list, tuple)):
                    # Handle simple lists
                    if all(
                        isinstance(item, (str, int, float, bool)) for item in attr_value
                    ):
                        attributes[attr_name] = list(attr_value)

        return attributes

    except Exception as e:
        print(f"Error extracting IFC attributes: {e}")
        return {}


def _extract_property_sets(ifc_entity) -> Dict[str, Dict[str, Any]]:
    """Extract property sets from an IFC entity."""
    try:
        import ifcopenshell.util.pset

        # Get all property sets
        psets = ifcopenshell.util.pset.get_psets(ifc_entity)

        # Filter out None values and ensure serializable types
        filtered_psets = {}
        for pset_name, properties in psets.items():
            if properties:
                filtered_props = {}
                for prop_name, prop_value in properties.items():
                    if prop_value is not None:
                        if isinstance(prop_value, (str, int, float, bool)):
                            filtered_props[prop_name] = prop_value
                        elif isinstance(prop_value, (list, tuple)):
                            if all(
                                isinstance(item, (str, int, float, bool))
                                for item in prop_value
                            ):
                                filtered_props[prop_name] = list(prop_value)

                if filtered_props:
                    filtered_psets[pset_name] = filtered_props

        return filtered_psets

    except Exception as e:
        print(f"Error extracting property sets: {e}")
        return {}


def _extract_type_info(ifc_entity) -> Dict[str, Any]:
    """Extract type information from an IFC entity."""
    try:
        import ifcopenshell.util.element
        import ifcopenshell.util.pset

        # Get relating type
        relating_type = ifcopenshell.util.element.get_type(ifc_entity)

        if not relating_type:
            return {}

        type_info = {}

        # Basic type information
        type_info["name"] = relating_type.Name
        type_info["class"] = relating_type.is_a()
        type_info["description"] = relating_type.Description

        # Type properties
        type_psets = ifcopenshell.util.pset.get_psets(relating_type)
        if type_psets:
            filtered_type_psets = {}
            for pset_name, properties in type_psets.items():
                if properties:
                    filtered_props = {}
                    for prop_name, prop_value in properties.items():
                        if prop_value is not None:
                            if isinstance(prop_value, (str, int, float, bool)):
                                filtered_props[prop_name] = prop_value
                            elif isinstance(prop_value, (list, tuple)):
                                if all(
                                    isinstance(item, (str, int, float, bool))
                                    for item in prop_value
                                ):
                                    filtered_props[prop_name] = list(prop_value)

                    if filtered_props:
                        filtered_type_psets[pset_name] = filtered_props

            if filtered_type_psets:
                type_info["properties"] = filtered_type_psets

        return type_info

    except Exception as e:
        print(f"Error extracting type info: {e}")
        return {}


def _extract_spatial_info(ifc_entity) -> Dict[str, Any]:
    """Extract spatial container and hierarchy information."""
    try:
        import ifcopenshell.util.element

        # Get spatial container
        container = ifcopenshell.util.element.get_container(ifc_entity)

        if not container:
            return {}

        spatial_info = {}

        # Container information
        spatial_info["container_name"] = container.Name
        spatial_info["container_class"] = container.is_a()
        spatial_info["container_description"] = container.Description

        # Build spatial hierarchy
        hierarchy = []
        current = container

        while current:
            hierarchy.append(
                {
                    "name": current.Name,
                    "class": current.is_a(),
                    "description": current.Description,
                }
            )
            current = ifcopenshell.util.element.get_container(current)

        if hierarchy:
            spatial_info["hierarchy"] = hierarchy

        return spatial_info

    except Exception as e:
        print(f"Error extracting spatial info: {e}")
        return {}


def _extract_material_info(ifc_entity) -> Dict[str, Any]:
    """Extract material information from an IFC entity."""
    try:
        import ifcopenshell.util.element
        import ifcopenshell.util.pset

        # Get material information
        materials = ifcopenshell.util.element.get_materials(ifc_entity)

        if not materials:
            return {}

        material_info = {}

        for i, material in enumerate(materials):
            material_data = {
                "name": material.Name,
                "description": getattr(material, "Description", None),
                "category": getattr(material, "Category", None),
            }

            # Get material properties
            material_psets = ifcopenshell.util.pset.get_psets(material)
            if material_psets:
                filtered_material_psets = {}
                for pset_name, properties in material_psets.items():
                    if properties:
                        filtered_props = {}
                        for prop_name, prop_value in properties.items():
                            if prop_value is not None:
                                if isinstance(prop_value, (str, int, float, bool)):
                                    filtered_props[prop_name] = prop_value
                                elif isinstance(prop_value, (list, tuple)):
                                    if all(
                                        isinstance(item, (str, int, float, bool))
                                        for item in prop_value
                                    ):
                                        filtered_props[prop_name] = list(prop_value)

                        if filtered_props:
                            filtered_material_psets[pset_name] = filtered_props

                if filtered_material_psets:
                    material_data["properties"] = filtered_material_psets

            # Remove None values
            material_data = {k: v for k, v in material_data.items() if v is not None}

            if material_data:
                material_key = f"material_{i}" if len(materials) > 1 else "material"
                material_info[material_key] = material_data

        return material_info

    except Exception as e:
        print(f"Error extracting material info: {e}")
        return {}


def validate_ifc_object(blender_object: Object) -> tuple[bool, str]:
    """
    Validate that a Blender object is a valid IFC element.
    """
    try:
        import bonsai.tool as tool

        if not blender_object:
            return False, "No object provided"

        if not hasattr(blender_object, "BIMObjectProperties"):
            return False, "Object has no BIM properties"

        if not blender_object.BIMObjectProperties.ifc_definition_id:
            return False, "Object has no IFC definition ID"

        if not tool.Ifc.get():
            return False, "No IFC file loaded"

        ifc_entity = tool.Ifc.get_entity(blender_object)
        if not ifc_entity:
            return False, "Cannot find IFC entity"

        return True, "Valid IFC object"

    except ImportError:
        return False, "Bonsai addon not available"
    except Exception as e:
        return False, f"Validation error: {e}"
