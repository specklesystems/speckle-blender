from typing import Deque, Dict, List, Optional, Set, Tuple, Union
import bpy
from bpy.types import Object, Collection, ID
from specklepy.objects.base import Base
from bpy_speckle.specklepy_extras.commit_object_builder import CommitObjectBuilder, ROOT
from specklepy.objects import Base
from specklepy.objects.other import Collection as SCollection
from attrs import define

ELEMENTS = "elements"

def _id(natvive_object: ID) -> str:
    #NOTE: to avoid naming collisions, we prefix collections and objects differently
    return f"{type(natvive_object).__name__}::{natvive_object.name_full}" 

def _try_id(natvive_object: Optional[Union[Collection, Object]]) -> Optional[str]:
    return _id(natvive_object) if natvive_object else None

def convert_collection_to_speckle(col: Collection) -> SCollection:
    convered_collection = SCollection(name = col.name_full, collectionType = "Blender Collection", elements = [])
    convered_collection.applicationId = _id(col)
    return convered_collection

@define(slots=True)
class BlenderCommitObjectBuilder(CommitObjectBuilder[Object]):

    _collections: Dict[str, SCollection]

    def __init__(self) -> None:
        super().__init__()
        self._collections = {}

    def include_object(self, conversion_result: Base, native_object: Object) -> None:

        # Set the Child -> Parent relationships
        parent = native_object.parent
        
        parent_collections: Tuple[Collection] = native_object.users_collection # type: ignore 
        parent_collection = parent_collections[0] if len(parent_collections) > 0 else None #NOTE: we don't support objects appearing in more than one collection, for now, we will just take the zeroth one
        
        app_id = _id(native_object)
        conversion_result.applicationId = app_id
        self.converted[app_id] = conversion_result

        # in order or priority, direct parent, direct parent collection, root
        self.set_relationship(app_id, (_try_id(parent), ELEMENTS), (_try_id(parent_collection), ELEMENTS), (ROOT, ELEMENTS))
        # if parent_collection:
        #     self._include_collection(parent_collection)

    def ensure_collection(self, col: Collection) -> SCollection:
        id = _id(col)
        if id in self._collections:
            return self._collections[id] # collection already converted!

         # Set the Parent -> Children relationships
        for c in col.children:
            #NOTE: There's no falling back to the grandparent, if the direct parent collection wasn't converted, then we we fallback to the root
            self.set_relationship(_id(c), (id, ELEMENTS), (ROOT, ELEMENTS)) 

        # Set Child -> Parent relationship
        # parent = self.find_collection_parent(col)
        # self.set_relationship(id, (_try_builder_id(parent), ELEMENTS), (ROOT, ELEMENTS)) 

        convered_collection = convert_collection_to_speckle(col)
        self.converted[id] = convered_collection
        self._collections[id] = convered_collection

        return convered_collection

    # def find_collection_parent(self, col: Collection) -> Optional[Collection]:
    #     for p in bpy.data.collections:
    #         if col.name in p.children.keys():
    #             return p
    #     return None

    #TODO: I've started an approach that will not work
    # Goal #1 get all collections sending
    # Sync with Claire, ask how we handle this in Rhino with partial selection of layers (proably how I'm expecting it works, but good to double check)
    # Goal #2 Figure out how to send collections
    # - all collections
    # - all collections that contain a child collection that has geometry...
    # - only collections explicitly selected

    def build_commit_object(self, root_commit_object: Base) -> None:
        assert(root_commit_object.applicationId in self.converted)

        # Create all collections
        for col in bpy.data.collections:
            self.ensure_collection(col)

        objects_to_build = set(self.converted.values())
        objects_to_build.remove(root_commit_object)

        self.apply_relationships(objects_to_build, root_commit_object)

        # Kill unused collections
        # useful_collections: Set[Collection] = set()
        # stack = Deque[Collection]

        # stack.append(root_commit_object)

        


        


    # def build_commit_object(self, root_commit_object: Base) -> None:

    #     convertedObjects = [x for x in self.converted.values()] # Converted objects, but no collections!
    #     for (id, col) in self._collections.items():
    #         self.converted[id] = col
        
    #     # Apply relationships for all non-collection objects
    #     self.apply_relationships(convertedObjects, root_commit_object)

    #     # Remove empty collections
    #     for (id, col) in self._collections.items(): #TODO: XXX: How to ensure empty collections are avoided! Potentially need to traverse from root object down...
    #         if not col.elements:
    #             self.converted.pop(id)

    #     self.apply_relationships(convertedObjects, root_commit_object)

    #     return