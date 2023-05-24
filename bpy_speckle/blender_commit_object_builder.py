from typing import Dict, List, Optional, Tuple, Union
from bpy.types import Object, Collection
from specklepy.objects.base import Base
from bpy_speckle.specklepy_extras.commit_object_builder import CommitObjectBuilder, ROOT
from specklepy.objects import Base
from specklepy.objects.other import Collection as SCollecton
from attrs import define

ELEMENTS = "elements"
blenderObject = Union[Object, Collection]

def _id(natvive_object: blenderObject) -> str:
    return natvive_object.name_full

def _try_id(natvive_object: Optional[blenderObject]) -> Optional[str]:
    if natvive_object:
        _id(natvive_object)
    else:
        return None

@define(slots=True, frozen=True)
class BlenderCommitObjectBuilder(CommitObjectBuilder[blenderObject]):

    _collections: Dict[str, SCollecton]

    def __init__(self) -> None:
        super().__init__()
        self._collections = []

    def include_object(self, conversion_result: Base, native_object: blenderObject) -> None:

        if isinstance(native_object, Collection):
            # Set the Parent -> Children relationships
            id = _id(native_object)
            for c in native_object.children:
                #NOTE: There's no falling back to the grandparent, if the direct parent collection wasn't converted, then we we fallback to the root
                self.set_relationship(_id(c), (id, ELEMENTS), (ROOT, ELEMENTS)) 
            assert(isinstance(conversion_result, SCollecton))
            self.collections.append(conversion_result)
            
        elif isinstance(native_object, Object):
            # Set the Child -> Parent relationships
            parent = None #native_object.parent

            parent_collections: Tuple[Collection] = native_object.users_collection
            parent_collection = parent_collections[0] if len(parent_collections) > 0 else None #NOTE: we don't support objects appearing in more than one collection, for now, we will just take the zeroth one
            
            app_id = _id(native_object)
            self.converted[app_id] = conversion_result
            # in order or priority, direct parent, direct parent collection, root
            self.set_relationship(app_id, (_try_id(parent), ELEMENTS), (_try_id(parent_collection), ELEMENTS), (ROOT, ELEMENTS))

        else:
            raise TypeError(f"Unsuported conversion_result type {type(conversion_result)}. Expected either Collection or Object")

    def build_commit_object(self, root_commit_object: Base) -> None:

        convertedObjects = [x for x in self.converted.values()] # Converted objects, but no collections!
        for (id, col) in self._collections.items():
            self.converted[id] = col
        
        # Apply relationships for all non-collection objects
        self.apply_relationships(convertedObjects, root_commit_object)

        for (id, col) in self._collections.items():
            if not col.elements:
                self.converted.pop(id)

        self.apply_relationships(convertedObjects, root_commit_object)

        return
