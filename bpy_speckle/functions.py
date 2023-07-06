from typing import Callable
from specklepy.objects.base import Base
from bpy_speckle.convert.constants import ELEMENTS_PROPERTY_ALIASES

from bpy_speckle.specklepy_extras.traversal import GraphTraversal, TraversalRule

"""
Speckle functions
"""

UNIT_SCALE = {
    "meters": 1.0,
    "centimeters": 0.01,
    "millimeters": 0.001,
    "inches": 0.0254,
    "feet": 0.3048,
    "kilometers": 1000.0,
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "km": 1000.0,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.340,
}

"""
Utility functions
"""


def _report(msg):
    """
    Function for printing messages to the console
    """
    print("SpeckleBlender: {}".format(msg))


def get_scale_length(units: str) -> float:
    if units.lower() in UNIT_SCALE.keys():
        return UNIT_SCALE[units]
    _report("Units <{}> are not supported.".format(units))
    return 1.0


"""
Client, user, and stream functions
"""


def get_default_traversal_func(can_convert_to_native: Callable[[Base], bool]) -> GraphTraversal:
    """
    Traversal func for traversing a speckle commit object
    """
    
    ignore_rule = TraversalRule(
    [
        lambda o: "Objects.Structural.Results" in o.speckle_type, #Sadly, this one is nessasary to avoid double conversion...
        lambda o: "Objects.BuiltElements.Revit.Parameter" in o.speckle_type, #This one is just for traversal performance of revit commits
    ], 
    lambda _: [],
    )

    convertable_rule = TraversalRule(
    [can_convert_to_native],
    lambda _: ELEMENTS_PROPERTY_ALIASES,
    )


    default_rule = TraversalRule(
    [lambda _: True],
    lambda o: o.get_member_names(), #TODO: avoid deprecated members
    )

    return GraphTraversal([ignore_rule, convertable_rule, default_rule])
