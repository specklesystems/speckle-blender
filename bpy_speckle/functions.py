from typing import Callable, List, Set
from bpy_speckle.clients import speckle_clients
from specklepy.objects.graph_traversal.traversal import GraphTraversal, TraversalRule
from specklepy.objects.base import Base

"""
Speckle functions
"""

unit_scale = {
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
    if units.lower() in unit_scale.keys():
        return unit_scale[units]
    _report("Units <{}> are not supported.".format(units))
    return 1.0


"""
Client, user, and stream functions
"""


def _check_speckle_client_user_stream(scene):
    """
    Verify that there is a valid user and stream
    """
    speckle = scene.speckle

    user = (
        speckle.users[int(speckle.active_user)]
        if len(speckle.users) > int(speckle.active_user)
        else None
    )

    if user is None:
        print("No users loaded.")

    stream = (
        user.streams[user.active_stream]
        if len(user.streams) > user.active_stream
        else None
    )

    if stream is None:
        print("Account contains no streams.")

    return (user, stream)


elements_aliases: Set[str] = {"elements", "@elements"}
ignore_props: Set[str] = {"@blockDefinition", "displayValue", "@displayValue", "units", "id", "applicationId"}

def get_default_traversal_func(can_convert_to_native: Callable[[Base], bool]) -> GraphTraversal:
    """
    Traversal func for traversing a speckle commit object
    """

    convertable_rule = TraversalRule(
    [can_convert_to_native],
    lambda _: [i for i in elements_aliases if i not in ignore_props],
    )

    ignore_result_rule = TraversalRule(
    [lambda o: "Objects.Structural.Results" in o.speckle_type, #Sadly, this one is nessasary to avoid double conversion...
    lambda o: "Objects.BuiltElements.Revit.Parameter" in o.speckle_type], #This one is just for traversal performance of revit commits
    lambda _: [],
    )

    default_rule = TraversalRule(
    [lambda _: True],
    lambda o: o.get_member_names(), #TODO: avoid deprecated members
    )

    return GraphTraversal([convertable_rule, ignore_result_rule, default_rule])