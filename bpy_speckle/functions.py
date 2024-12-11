from typing import Callable

from specklepy.objects.base import Base
from specklepy.objects.graph_traversal.traversal import GraphTraversal, TraversalRule
from specklepy.objects.units import get_scale_factor_to_meters, get_units_from_string

from bpy_speckle.convert.constants import ELEMENTS_PROPERTY_ALIASES


def _report(msg: object) -> None:
    """
    Function for printing messages to the console
    """
    print("SpeckleBlender: {}".format(msg))


def get_scale_length(units: str) -> float:
    """Returns a scalar to convert distance values from one unit system to meters"""
    return get_scale_factor_to_meters(get_units_from_string(units))


def get_default_traversal_func(
    can_convert_to_native: Callable[[Base], bool]
) -> GraphTraversal:
    """
    Traversal func for traversing a speckle commit object
    """

    ignore_rule = TraversalRule(
        [
            lambda o: "Objects.Structural.Results"
            in o.speckle_type,  # Sadly, this one is necessary to avoid double conversion...
            lambda o: "Objects.BuiltElements.Revit.Parameter"
            in o.speckle_type,  # This one is just for traversal performance of revit commits
        ],
        lambda _: [],
    )

    convertible_rule = TraversalRule(
        [can_convert_to_native],
        lambda _: ELEMENTS_PROPERTY_ALIASES,
    )

    default_rule = TraversalRule(
        [lambda _: True],
        lambda o: o.get_member_names(),  # TODO: avoid deprecated members
    )

    return GraphTraversal([ignore_rule, convertible_rule, default_rule])
