from typing import Iterator, TypeVar, Type
from specklepy.objects.base import Base
from specklepy.objects.graph_traversal.traversal import TraversalContext


def get_ascendants(context: TraversalContext) -> Iterator[Base]:
    """
    Walks up the tree, returning all ascendants, including context
    """
    head = context
    while head is not None:
        yield head.current
        head = head.parent


T = TypeVar("T", bound=Base)


def get_ascendant_of_type(context: TraversalContext, type_cls: Type[T]) -> Iterator[T]:
    """
    Walks up the tree, returning all ascendants of the given type,
    starting with the context, walking up parent nodes
    """
    for ascendant in get_ascendants(context):
        if isinstance(ascendant, type_cls):
            yield ascendant
