"""
All IFC-related imports are wrapped in try-except blocks to ensure the code only runs when Bonsai/ifcopenshell is available.
"""

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

        properties = {}

        # extract element attributes
        attributes = _get_attributes(ifc_entity)
        if attributes:
            properties["Attributes"] = attributes

        # extract element property sets
        property_sets = _get_ifc_object_properties(ifc_entity)
        if property_sets:
            properties["Property Sets"] = property_sets

        # extract element type property sets
        type_property_sets = _get_ifc_element_type_properties(ifc_entity)
        if type_property_sets:
            properties["Element Type Property Sets"] = type_property_sets

        # extract element type attributes
        type_attributes = _get_element_type_attributes(ifc_entity)
        if type_attributes:
            properties["Element Type Attributes"] = type_attributes

        return properties

    except ImportError:
        # Bonsai/ifcopenshell not available, silently return empty dict
        return {}
    except Exception as e:
        # Other errors, log and return empty dict
        print(f"Error extracting IFC properties: {e}")
        return {}


def _get_attributes(element) -> Dict[str, Any]:
    """
    Extract direct attributes from IFC element.
    """
    try:
        # Use scalar_only=True for performance as per documentation
        return element.get_info(True, False, scalar_only=True)
    except Exception as e:
        print(f"Error extracting attributes: {e}")
        return {}


def _get_ifc_object_properties(element) -> Dict[str, Dict[str, Any]]:
    """
    Extract properties from element's direct property relationships.
    """
    try:
        properties = {}

        # Process IsDefinedBy relationships
        if hasattr(element, "IsDefinedBy"):
            for relationship in element.IsDefinedBy:
                # Filter for IfcRelDefinesByProperties
                if relationship.is_a("IfcRelDefinesByProperties"):
                    relating_property_definition = (
                        relationship.RelatingPropertyDefinition
                    )
                    # Filter for IfcPropertySet definitions
                    if relating_property_definition.is_a("IfcPropertySet"):
                        pset_name = relating_property_definition.Name
                        if pset_name and hasattr(
                            relating_property_definition, "HasProperties"
                        ):
                            pset_properties = _get_properties(
                                relating_property_definition
                            )
                            if pset_properties:
                                properties[pset_name] = pset_properties

        return properties

    except Exception as e:
        print(f"Error extracting object properties: {e}")
        return {}


def _get_ifc_element_type_properties(element) -> Dict[str, Dict[str, Any]]:
    """
    Extract properties from element type's property sets.
    """
    try:
        import ifcopenshell.util.element

        properties = {}

        # Get relating type
        relating_type = ifcopenshell.util.element.get_type(element)
        if not relating_type:
            return {}

        # Iterate through HasPropertySets relationship
        if hasattr(relating_type, "HasPropertySets"):
            for property_set in relating_type.HasPropertySets:
                # Filter for IfcPropertySet types only
                if property_set.is_a("IfcPropertySet"):
                    pset_name = property_set.Name
                    if pset_name and hasattr(property_set, "HasProperties"):
                        pset_properties = _get_properties(property_set)
                        if pset_properties:
                            properties[pset_name] = pset_properties

        return properties

    except Exception as e:
        print(f"Error extracting element type properties: {e}")
        return {}


def _get_element_type_attributes(element) -> Dict[str, Any]:
    """
    Extract attributes from element type definition.
    """
    try:
        import ifcopenshell.util.element

        # Get relating type
        relating_type = ifcopenshell.util.element.get_type(element)
        if not relating_type:
            return {}

        # Extract attributes using scalar_only=True
        return relating_type.get_info(True, False, scalar_only=True)

    except Exception as e:
        print(f"Error extracting element type attributes: {e}")
        return {}


def _get_properties(properties_container) -> Dict[str, Any]:
    """
    core property value extraction function.

    Handles 3 IFC property types:
    - IfcPropertySingleValue: Single property values
    - IfcPropertyListValue: List of property values
    - IfcPropertyEnumeratedValue: Enumerated property values
    """
    try:
        properties = {}

        if not hasattr(properties_container, "HasProperties"):
            return {}

        for prop in properties_container.HasProperties:
            prop_name = prop.Name
            if not prop_name:
                continue

            prop_value = None

            # Handle IfcPropertySingleValue
            if prop.is_a("IfcPropertySingleValue"):
                if hasattr(prop, "NominalValue") and prop.NominalValue is not None:
                    prop_value = prop.NominalValue
                    # Unwrap wrappedValue if present
                    if hasattr(prop_value, "wrappedValue"):
                        prop_value = prop_value.wrappedValue

            # Handle IfcPropertyListValue
            elif prop.is_a("IfcPropertyListValue"):
                if hasattr(prop, "ListValues") and prop.ListValues:
                    list_values = []
                    for list_item in prop.ListValues:
                        item_value = list_item
                        # Unwrap wrappedValue if present
                        if hasattr(item_value, "wrappedValue"):
                            item_value = item_value.wrappedValue
                        if item_value is not None:
                            list_values.append(item_value)
                    if list_values:
                        prop_value = list_values

            # Handle IfcPropertyEnumeratedValue
            elif prop.is_a("IfcPropertyEnumeratedValue"):
                if hasattr(prop, "EnumerationValues") and prop.EnumerationValues:
                    enum_values = []
                    for enum_item in prop.EnumerationValues:
                        item_value = enum_item
                        # Unwrap wrappedValue if present
                        if hasattr(item_value, "wrappedValue"):
                            item_value = item_value.wrappedValue
                        if item_value is not None:
                            enum_values.append(item_value)
                    if enum_values:
                        prop_value = (
                            enum_values if len(enum_values) > 1 else enum_values[0]
                        )

            # Add property if value was successfully extracted
            if prop_value is not None:
                properties[prop_name] = prop_value

        return properties

    except Exception as e:
        print(f"Error extracting properties from container: {e}")
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
