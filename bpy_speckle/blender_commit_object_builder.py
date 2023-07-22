from typing import Dict, Optional, Tuple, Union
import bpy
from bpy.types import Object, Collection, ID
from specklepy.objects.base import Base
from bpy_speckle.functions import _report
from bpy_speckle.specklepy_extras.commit_object_builder import CommitObjectBuilder, ROOT
from specklepy.objects import Base
from specklepy.objects.other import Collection as SCollection
from attrs import define

ELEMENTS = "elements"

def _id(natvive_object: ID) -> str:
    #NOTE: to avoid naming collisions, we prefix collections and objects differently
    return f"{type(natvive_object).__name__}:{natvive_object.name_full}" 

def _try_id(natvive_object: Optional[Union[Collection, Object]]) -> Optional[str]:
    return _id(natvive_object) if natvive_object else None

def convert_collection_to_speckle(col: Collection) -> SCollection:
    convered_collection = SCollection(name = col.name_full, collectionType = "Blender Collection", elements = [])
    convered_collection.applicationId = _id(col)

    color_tag = col.color_tag
    if color_tag and color_tag != "NONE":
        convered_collection["colorTag"] = col.color_tag

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

    def build_commit_object(self, root_commit_object: Base) -> None:
        assert(root_commit_object.applicationId in self.converted)

        # Create all collections
        root_col = self.ensure_collection(bpy.context.scene.collection)
        root_col.collectionType = "Scene Collection"
        for col in bpy.context.scene.collection.children_recursive:
            self.ensure_collection(col)

        objects_to_build = set(self.converted.values())
        objects_to_build.remove(root_commit_object)

        self.apply_relationships(objects_to_build, root_commit_object)

        assert(isinstance(root_commit_object, SCollection))
        # Kill unused collections

        def should_remove_unuseful_collection(col: SCollection) -> bool: #TODO: this maybe could be optimised
            elements = col.elements
            if not elements: return True

            should_remove_this_col = True

            i = 0
            while i < len(elements):
                c = elements[i]
                if not isinstance(c, SCollection): 
                    # col has objects (c)
                    should_remove_this_col = False
                    i += 1
                    continue

                if should_remove_unuseful_collection(c):
                    # c is not useful, kill it
                    del elements[i]
                else:
                    # col has a child (c) with objects
                    should_remove_this_col = False
                    i += 1
                    continue
        
            return should_remove_this_col

        if should_remove_unuseful_collection(root_commit_object):
            _report("WARNING: Only empty collections have been converted!") #TODO: consider raising exception here, to halt the send operation
