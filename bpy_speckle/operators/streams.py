"""
Stream operators
"""
from itertools import chain
from math import radians
from deprecated import deprecated
from typing import Any, Callable, Dict, Iterable, List, Optional, Union, cast
import webbrowser
import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
)
from bpy.types import (
    Context,
    Object,
    Collection
)
from bpy_speckle.blender_commit_object_builder import BlenderCommitObjectBuilder
from bpy_speckle.convert.to_native import (
    can_convert_to_native,
    convert_to_native,
    set_convert_instances_as,
)
from bpy_speckle.convert.to_speckle import (
    ConversionSkippedException,
    convert_to_speckle,
)
from bpy_speckle.functions import (
    _check_speckle_client_user_stream,
    get_default_traversal_func,
    get_scale_length,
    _report,
)
from bpy_speckle.clients import speckle_clients
from bpy_speckle.operators.users import add_user_stream
from bpy_speckle.properties.scene import SpeckleSceneSettings
from bpy_speckle.convert.util import link_object_to_collection_nested

from specklepy.api.models import Commit
from specklepy.api import operations, host_applications
from specklepy.api.wrapper import StreamWrapper
from specklepy.api.resources.stream import Stream
from specklepy.transports.server import ServerTransport
from specklepy.objects.graph_traversal.traversal import TraversalContext
from specklepy.objects import Base
from specklepy.objects.other import Collection as SCollection
from specklepy.logging.exceptions import SpeckleException
from specklepy.logging import metrics

@deprecated
def get_objects_collections(base: Base) -> Dict[str, list]:
    """Create collections based on the dynamic members on a root commit object"""
    collections = {}
    for name in base.get_dynamic_member_names():
        value = base[name]
        if isinstance(value, list):
            col = get_or_create_collection(name)
            collections[name] = get_objects_nested_lists(value, col)
        if isinstance(value, Base):
            col = get_or_create_collection(name)
            collections[name] = get_objects_collections_recursive(value, col)

    return collections

@deprecated
def get_objects_nested_lists(items: list, parent_col: Optional[bpy.types.Collection] = None) -> List:
    """For handling the weird nested lists that come from Grasshopper"""
    objects = []
    if not items:
        return objects

    if isinstance(items[0], list):
        items = list(chain.from_iterable(items))
        objects.extend(get_objects_nested_lists(items, parent_col))
    else:
        objects = [
            get_objects_collections_recursive(item, parent_col)
            for item in items
            if isinstance(item, Base)
        ]

    return objects

@deprecated
def get_objects_collections_recursive(base: Base, parent_col: Optional[bpy.types.Collection] = None) -> List:
    """Recursively create collections based on the dynamic members on nested `Base` objects within the root commit object"""
    # if it's a convertable (registered) class and not just a plain `Base`, return the object itself
    if can_convert_to_native(base):
        return [base]

    # if it's an unknown type, try to drill further down to find convertable objects
    objects = []

    for name in base.get_dynamic_member_names():
        value = base[name]
        if isinstance(value, list):
            objects.extend(item for item in value if isinstance(item, Base))
        if isinstance(value, Base):
            col = parent_col.children.get(name)
            if not col:
                col = get_or_create_collection(name)
                try:
                    parent_col.children.link(col)
                except:
                    _report(
                        f"Problem linking collection {col.name} to parent {parent_col.name}; skipping"
                    )
            objects.append({name: get_objects_collections_recursive(value, col)})

    return objects


ObjectCallback = Optional[Callable[[bpy.types.Context, Object, Base], Object]]
ReceiveCompleteCallback = Optional[Callable[[bpy.types.Context, Dict[str, Union[Object, Collection]]], None]]

def get_receive_funcs(speckle: SpeckleSceneSettings) -> tuple[ObjectCallback, ReceiveCompleteCallback]:
        """
        Fetches the injected callback functions from user specified "Receive Script"
        """

        objectCallback: ObjectCallback = None
        receiveCompleteCallback: ReceiveCompleteCallback = None
        
        if speckle.receive_script in bpy.data.texts:
            mod = bpy.data.texts[speckle.receive_script].as_module()
            if hasattr(mod, "execute_for_each"):
                objectCallback = mod.execute_for_each
            elif hasattr(mod, "execute"): 
                objectCallback = lambda c, o, _ : mod.execute(c.scene, o)

            if hasattr(mod, "execute_for_all"):
                receiveCompleteCallback = mod.execute_for_all

        return (objectCallback, receiveCompleteCallback)

@deprecated
def bases_to_native(context: bpy.types.Context, collections: Dict[str, list], scale: float, stream_id: str, func: ObjectCallback = None):
    for col_name, objects in collections.items():
        col = bpy.data.collections[col_name]
        existing = get_existing_collection_objs(col)
        if isinstance(objects, dict):
            bases_to_native(context, objects, scale, stream_id)
        elif isinstance(objects, list):
            for obj in objects:
                if isinstance(obj, dict):
                    bases_to_native(context, obj, scale, stream_id, func)
                elif isinstance(obj, list): #FIXME: wtf are these nested if statement, can this not be a recursive call?
                    for item in obj:
                        if isinstance(item, dict):
                            bases_to_native(context, item, scale, stream_id, func)
                        elif isinstance(item, Base):
                            base_to_native(
                                context, item, scale, stream_id, col, existing, func
                            )
                elif isinstance(obj, Base):
                    base_to_native(context, obj, scale, stream_id, col, existing, func)

                else:
                    _report(
                        f"Something went wrong when receiving collection: {col_name}" #FIXME: undescript report message
                    )

            bpy.context.view_layer.update()

            if context.area:
                context.area.tag_redraw()


@deprecated
def base_to_native(context: bpy.types.Context,
    base: Base,
    scale: float,
    stream_id: str,
    col: bpy.types.Collection,
    existing: Dict[str, Object],
    func: ObjectCallback = None
    ):

    new_objects = convert_to_native(base)

    #NOTE: this code is ancient, and in testing does nothing, so we are removing it.
    # if hasattr(base, "properties") and base.properties is not None: 
    #     new_objects.extend(get_speckle_subobjects(base.properties, scale, base.id))
    # elif isinstance(base, dict) and "properties" in base.keys():
    #     new_objects.extend(
    #          get_speckle_subobjects(base["properties"], scale, base["id"])
    #      )
 
    """
    Set object Speckle settings
    """
    for new_object in new_objects:
        if new_object is None:
            continue

        """
        Run injected function
        """
        if func:
            new_object = func(context, new_object, base) #this base object isn't always the right one for hosted elements! #TODO: may be it now, need to double check!

        if (
            new_object is None
        ):  # If the injected function returned None, then we should ignore this object.
            _report(f"Script '{func.__module__}' returned None.")
            continue

        new_object.speckle.stream_id = stream_id
        new_object.speckle.send_or_receive = "receive"

        if new_object.speckle.object_id in existing.keys():
            name = existing[new_object.speckle.object_id].name
            existing[new_object.speckle.object_id].name = f"{name}__deleted"
            new_object.name = name
            col.objects.unlink(existing[new_object.speckle.object_id])

        link_object_to_collection_nested(new_object, col)
        #if new_object.name not in col.objects:
            #col.objects.link(new_object)


def _add_to_heirarchy(converted: Union[Object, Collection], traversalContext : TraversalContext, converted_objects: Dict[str, Union[Object, Collection]]):
    nextParent = traversalContext.parent

    # Traverse up the tree to find a direct parent object, and a containing collection
    parent_collection: Optional[Collection] = None
    parent_object: Optional[Object] = None

    while nextParent:
        if nextParent.current.id in converted_objects:
            c = converted_objects[nextParent.current.id]

            if isinstance(c, Collection):
                parent_collection = c
                break
            else: #isinstance(c, Object):
                parent_object = parent_object or c

        nextParent = nextParent.parent

    # If no containing collection is found, fall back to the scene collection
    if not parent_collection:
        parent_collection = bpy.context.scene.collection

    if isinstance(converted, Object):
        if parent_object:
            converted.parent = parent_object
        link_object_to_collection_nested(converted, parent_collection)
    else: #isinstance(converted, Collection):
        parent_collection.children.link(converted)
    

def collection_to_native(collection: SCollection) -> Collection: 
    name = collection.name or collection.applicationId
    
    return get_or_create_collection(name)

def get_or_create_collection(name: str, clear_collection: bool = True) -> Collection:
    existing = bpy.data.collections.get(name)
    if existing:
        if clear_collection:
            for obj in existing.objects:
                existing.objects.unlink(obj)
        return existing
    else:
        new_collection = bpy.data.collections.new(name)

        #HACK: We want to not render revit "Rooms" collections by default.
        if name == "Rooms":
            new_collection.hide_viewport = True
            new_collection.hide_render = True

        return new_collection



def create_child_collections(parent_col: bpy.types.Collection, children_names: Iterable[str]):
    for name in children_names:
        col = get_or_create_collection(name)
        parent_col.children.link(col)

@deprecated
def get_existing_collection_objs(col: bpy.types.Collection) -> Dict[str, bpy.types.Object]:
    return {
        obj.speckle.object_id: obj for obj in col.objects if obj.speckle.object_id != ""
    }


def get_collection_parents(collection: bpy.types.Collection, names: list[str]) -> None:
    for parent in bpy.data.collections:
        if collection.name in parent.children.keys():
            # TODO: this should be rethought to make it clear when this is an IFC delim so we know to replace it
            # with `/` again on receive
            names.append(parent.name.replace("/", "::").replace(".", "::"))
            get_collection_parents(parent, names)


def get_collection_hierarchy(collection: Optional[bpy.types.Collection]) -> list[str]:
    if not collection:
        return []
    names = [collection.name.replace("/", "::").replace(".", "::")]
    get_collection_parents(collection, names)

    return names


def create_nested_hierarchy(base: Base, hierarchy: List[str], objects: Any):
    child = base

    while hierarchy:
        name = hierarchy.pop()
        if not hasattr(child, name):
            child[name] = Base()
            child.add_detachable_attrs({name})
        child = child[name]

    if not hasattr(child, "@elements"):
        child["@elements"] = []
    child["@elements"].extend(objects)

    return base

#RECEIVE_MODES = [#TODO: modes
#    ("create", "Create", "Add new geometry, without removing any existing objects"),
#    ("replace", "Replace", "Replace objects from previous receive operations from the same stream"),
#    #("update","Update", "") #TODO: update mode!
#]

INSTANCES_SETTINGS = [
    ("collection_instance", "Collection Instace", "Receive Instances as Collection Instances"),
    ("linked_duplicates", "Linked Duplicates", "Receive Instances as Linked Duplicates"),
]

class ReceiveStreamObjects(bpy.types.Operator):
    """
    Receive stream objects
    """

    bl_idname = "speckle.receive_stream_objects"
    bl_label = "Download Stream Objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Receive objects from active stream"

    
    clean_meshes: BoolProperty(name="Clean Meshes", default=False)

    #receive_mode: EnumProperty(items=RECEIVE_MODES, name="Receive Type", default="replace", description="The behaviour of the recieve operation")
    receive_instances_as: EnumProperty(items=INSTANCES_SETTINGS, name="Receive Instances As", default="collection_instance", description="How to receive speckle Instances")
    

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "clean_meshes")
        #col.prop(self, "receive_mode")
        col.prop(self, "receive_instances_as")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    @staticmethod
    def clean_converted_meshes(context: bpy.types.Context, convertedObjects: dict[str, Object]):
        
        bpy.ops.object.select_all(action='DESELECT')

        active = None
        for obj in convertedObjects.values():
            if obj.type != 'MESH':
                continue

            obj.select_set(True, view_layer=context.scene.view_layers[0])
            active = obj
        

        if active == None:
            return
        context.view_layer.objects.active = active

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.dissolve_limited(angle_limit=radians(0.1))

        # Reset state to previous (not quite sure if this is 100% necessary)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = None

    def execute(self, context):
        try:
            self.receive(context)
            return {"FINISHED"}
        except Exception as ex:
            _report(f"Failed to receive objects: {ex}")
            return {"CANCELLED"}

    def receive(self, context: Context):
        bpy.context.view_layer.objects.active = None

        speckle: SpeckleSceneSettings = context.scene.speckle
        
        #Get UI Selection
        (user, stream, branch, commit) = speckle.validate_commit_selection()

        #Get actual stream data
        client = speckle_clients[int(speckle.active_user)]

        transport = ServerTransport(stream.id, client)

        metrics.track(
            metrics.RECEIVE,
            getattr(transport, "account", None), 
            custom_props={
                "sourceHostApp": host_applications.get_host_app_from_string(commit.source_application).slug,
                "sourceHostAppVersion": commit.source_application,
                "isMultiplayer": commit.author_id != user.id,
            },
        )
        commit_object = operations._untracked_receive(commit.referenced_object, transport)
        client.commit.received(
            stream.id,
            commit.id,
            source_application="blender",
            message="received commit from Speckle Blender",
        )

        context.window_manager.progress_begin(0, commit_object.totalChildrenCount or 1)

        set_convert_instances_as(self.receive_instances_as) #HACK: we need a better way to pass settings down to the converter

        traversalFunc = get_default_traversal_func(can_convert_to_native)
        converted_objects: Dict[str, Union[Object, Collection]] = {}
        converted_count: int = 0
        (object_converted_callback, on_complete_callback) = get_receive_funcs(speckle)

        #HACK: ensure commit object has a name if not already
        if not getattr(commit_object, "name", None):
            commit_object["name"] = "{} [ {} @ {} ]".format(stream.name, branch.name, commit.id) # Matches Rhino "Create" naming

        for item in traversalFunc.traverse(commit_object):
            
            current: Base = item.current
            if can_convert_to_native(current) or isinstance(current, SCollection):
                try:
                    if not current or not current.id: raise Exception("{current} was an invalid speckle object")

                    #Convert the object!
                    converted: Union[Object, Collection, None]
                    if isinstance(current, SCollection):
                        converted = collection_to_native(current)
                    else:
                        converted = convert_to_native(current)

                        #Run the user specified callback function (AKA receive script)
                        if object_converted_callback:
                            converted = object_converted_callback(context, converted, current)
                    
                    if converted is None:
                        raise Exception("Conversion returned None")
                        
                    converted_objects[current.id] = converted

                    _add_to_heirarchy(converted, item, converted_objects)

                except Exception as ex: 
                    _report(f"Conversion of {current.speckle_type} {current} failed: {ex}")

            converted_count += 1
            context.window_manager.progress_update(converted_count) #NOTE: We don't expect to ever reach 100% since not every object will be traversed


        context.window_manager.progress_end()

        if self.clean_meshes:
            objects = {k: v for k, v in converted_objects.items() if isinstance(v, Object)}
            self.clean_converted_meshes(context, objects)

        if on_complete_callback:
            on_complete_callback(context, converted_objects)

        return {"FINISHED"}



        """
        Create or get Collection for stream objects
        """
        collections = get_objects_collections(commit_object)

        if not collections:
            print("Unusual commit structure - did not correctly create collections")
            return {"CANCELLED"}

        # name = ""
        # if self.receive_mode == "create":
        name = "{} [ {} @ {} ]".format(stream.name, branch.name, commit.id) # Matches Rhino "Create" naming
        # else:
        #     name = stream.name # Doesn't quite match rhino's Update layer naming, but is close enough no? 

        col = get_or_create_collection(name)
        col.speckle.stream_id = stream.id
        col.speckle.units = commit_object.units or "m"
            
        if col.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(col)

        for child_col in collections.keys():
            try:
                col.children.link(bpy.data.collections[child_col])
            except:
                pass
        """
        Set conversion scale from stream units
        """
        scale = (
            get_scale_length(col.speckle.units)
            / context.scene.unit_settings.scale_length
        )

        """
        Get script from text editor for injection
        """
        created_objects = {}
        (func, on_complete) = get_receive_funcs(context, created_objects)
        

        """
        Iterate through retrieved resources
        """

        bases_to_native(context, collections, scale, stream.id, func)
        context.window_manager.progress_end()

        if self.clean_meshes:
            self.clean_converted_meshes(context, created_objects)

        if on_complete:
            on_complete(context, created_objects)


        return {"FINISHED"}



class SendStreamObjects(bpy.types.Operator):
    """
    Send stream objects
    """

    bl_idname = "speckle.send_stream_objects"
    bl_label = "Send stream objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Send selected objects to active stream"

    apply_modifiers: BoolProperty(name="Apply modifiers", default=True)
    commit_message: StringProperty(
        name="Message",
        default="Pushed elements from Blender.",
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "commit_message")
        col.prop(self, "apply_modifiers")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            N = len(context.selected_objects)
            if N == 1:
                self.commit_message = f"Pushed {N} element from Blender."
            else:
                self.commit_message = f"Pushed {N} elements from Blender."
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        try:
            self.send(context)
            return {"FINISHED"}
        except Exception as ex:
            _report(f"Send failed: {ex}")
            return {"CANCELLED"} 

    def send(self, context: Context) -> str:

        selected = context.selected_objects
        if len(selected) < 1:
            raise Exception("No objects are selected, sending canceled")

        speckle = cast(SpeckleSceneSettings, context.scene.speckle)
        (user, stream, branch) = speckle.validate_branch_selection()

        client = speckle_clients[int(speckle.active_user)]

        #TODO: Check how units scalling should works
        # scale = context.scene.unit_settings.scale_length / get_scale_length(
        #     stream.units.lower()
        # )

        scale = 1.0

        units = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

        # Get script from text editor for injection
        func = None
        if speckle.send_script in bpy.data.texts:
            mod = bpy.data.texts[speckle.send_script].as_module()
            if hasattr(mod, "execute"):
                func = mod.execute

        num_converted = 0
        context.window_manager.progress_begin(0, max(len(selected), 1))

        depsgraph = bpy.context.evaluated_depsgraph_get() if self.apply_modifiers else None

        commit_builder = BlenderCommitObjectBuilder()
        for obj in selected:
            try:
                # Run injected function
                new_object = obj
                if func:
                    new_object = func(context.scene, obj)

                    if (new_object is None):
                        raise ConversionSkippedException(f"Script '{func.__module__}' returned None.")

                converted = convert_to_speckle(
                    obj,
                    scale,
                    units,
                    depsgraph
                )

                if not converted:
                    raise Exception("Converter returned None")

                commit_builder.include_object(converted, obj)

                _report(f"Successfully converted '{obj.name_full}'\tas '{converted.speckle_type}'")
            except ConversionSkippedException as ex:
                _report(f"Skipped converting '{obj.name_full}': '{ex}'")
            except Exception as ex:
                _report(f"Failed to converted '{obj.name_full}': '{ex}'")
                
            num_converted += 1
            context.window_manager.progress_update(num_converted)

        context.window_manager.progress_end()

        commit_object = Base()
        commit_builder.build_commit_object(commit_object)

        _report(f"Sending data to {stream.name}")
        transport = ServerTransport(stream.id, client)
        OBJECT_ID = operations.send(
            commit_object,
            [transport],
        )

        COMMIT_ID = client.commit.create(
            stream.id,
            OBJECT_ID,
            branch.name,
            message=self.commit_message,
            source_application="blender",
        )
        _report(f"Commit Created {user.server_url}/streams/{stream.id}/commits/{COMMIT_ID}")

        bpy.ops.speckle.load_user_streams() # refresh loaded commits
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        return COMMIT_ID

        base = Base()
        for name, objects in export.items():
            collection = bpy.data.collections.get(name)
            hierarchy = get_collection_hierarchy(collection)
            create_nested_hierarchy(base, hierarchy, objects)

        transport = ServerTransport(stream.id, client)

        _report(f"Sending to {stream}")
        obj_id = operations.send(
            base,
            [transport],
        )

        commitId = client.commit.create(
            stream.id,
            obj_id,
            branch.name,
            message=self.commit_message,
            source_application="blender",
        )
        _report(f"Commit Created {user.server_url}/streams/{stream.id}/commits/{commitId}")

        bpy.ops.speckle.load_user_streams()

        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ViewStreamDataApi(bpy.types.Operator):
    bl_idname = "speckle.view_stream_data_api"
    bl_label = "Open Stream in Web"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "View the stream in the web browser"

    def execute(self, context):

        if len(context.scene.speckle.users) > 0:
            user = context.scene.speckle.users[int(context.scene.speckle.active_user)]
            if len(user.streams) > 0:
                stream = user.streams[user.active_stream]

                webbrowser.open("%s/streams/%s" % (user.server_url, stream.id), new=2)
                return {"FINISHED"}
        return {"CANCELLED"}


class AddStreamFromURL(bpy.types.Operator):
    """
    Add / select a stream using its url
    """

    bl_idname = "speckle.add_stream_from_url"
    bl_label = "Add stream from URL"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Add an existing stream by providing its URL"
    stream_url: StringProperty(
        name="Stream URL", default="https://speckle.xyz/streams/3073b96e86"
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "stream_url")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        speckle = context.scene.speckle

        wrapper = StreamWrapper(self.stream_url)
        user_index = next(
            (i for i, u in enumerate(speckle.users) if wrapper.host in u.server_url),
            None,
        )
        if user_index is None:
            return {"CANCELLED"}
        speckle.active_user = str(user_index)
        user = speckle.users[user_index]

        client = speckle_clients[user_index]
        stream = client.stream.get(wrapper.stream_id, branch_limit=20)
        if not isinstance(stream, Stream):
            raise SpeckleException("Could not get the requested stream")

        index, b_stream = next(
            ((i, s) for i, s in enumerate(user.streams) if s.id == stream.id),
            (None, None),
        )

        if index is None:
            add_user_stream(user, stream)
            user.active_stream, b_stream = next(
                (i, s) for i, s in enumerate(user.streams) if s.id == stream.id
            )
        else:
            user.active_stream = index

        if wrapper.branch_name:
            b_index = b_stream.branches.find(wrapper.branch_name)
            b_stream.branch = str(b_index if b_index != -1 else 0)
        elif wrapper.commit_id:
            commit = client.commit.get(wrapper.stream_id, wrapper.commit_id)
            if isinstance(commit, Commit):
                b_index = b_stream.branches.find(commit.branchName)
                if b_index == -1:
                    b_index = 0
                b_stream.branch = str(b_index)
                c_index = b_stream.branches[b_index].commits.find(commit.id)
                b_stream.branches[b_index].commit = str(c_index if c_index != -1 else 0)

        # Update view layer
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        return {"FINISHED"}


class CreateStream(bpy.types.Operator):
    """
    Create new stream
    """

    bl_idname = "speckle.create_stream"
    bl_label = "Create stream"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Create new stream"

    stream_name: StringProperty(name="Stream name")
    stream_description: StringProperty(
        name="Stream description", default="This is a Blender stream."
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "stream_name")
        col.prop(self, "stream_description")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):

        check = _check_speckle_client_user_stream(context.scene)
        if check is None:
            return {"CANCELLED"}

        user, bstream = check

        client = speckle_clients[int(context.scene.speckle.active_user)]

        client.stream.create(
            name=self.stream_name, description=self.stream_description, is_public=True
        )

        bpy.ops.speckle.load_user_streams()
        user.active_stream = user.streams.find(self.stream_name)

        # Update view layer
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        return {"FINISHED"}


class DeleteStream(bpy.types.Operator):
    """
    Delete stream
    """

    bl_idname = "speckle.delete_stream"
    bl_label = "Delete stream"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Delete selected stream permanently"

    are_you_sure: BoolProperty(
        name="Confirm",
        default=False,
    )

    delete_collection: BoolProperty(name="Delete collection", default=False)

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "are_you_sure")
        col.prop(self, "delete_collection")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):

        if not self.are_you_sure:
            return {"CANCELLED"}

        self.are_you_sure = False

        check = _check_speckle_client_user_stream(context.scene)
        if check is None:
            return {"CANCELLED"}

        user, stream = check
        client = speckle_clients[int(context.scene.speckle.active_user)]

        client.stream.delete(id=stream.id)

        if self.delete_collection:
            col_name = "SpeckleStream_{}_{}".format(stream.name, stream.id)
            if col_name in bpy.data.collections:
                collection = bpy.data.collections[col_name]
                bpy.data.collections.remove(collection)

        bpy.ops.speckle.load_user_streams()
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class SelectOrphanObjects(bpy.types.Operator):
    """
    Select Speckle objects that don't belong to any stream
    """

    bl_idname = "speckle.select_orphans"
    bl_label = "Select orphaned objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select Speckle objects that don't belong to any stream"

    def draw(self, context):
        layout = self.layout

    def execute(self, context):

        for o in context.scene.objects:
            if (
                o.speckle.stream_id
                and o.speckle.stream_id not in context.scene["speckle_streams"]
            ):
                o.select = True
            else:
                o.select = False

        return {"FINISHED"}


class UpdateGlobal(bpy.types.Operator):
    """
    DEPRECATED
    Update all Speckle objects
    """

    bl_idname = "speckle.update_global"
    bl_label = "Update Global"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Update all Speckle objects"

    client = None

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        label = row.label(text="Update everything.")

    def execute(self, context):

        client = context.scene.speckle.client

        profiles = client.load_local_profiles()
        if len(profiles) < 1:
            raise ValueError("No profiles found.")
        client.use_existing_profile(sorted(profiles.keys())[0])
        context.scene.speckle.user = sorted(profiles.keys())[0]

        for obj in context.scene.objects:
            if obj.speckle.enabled:
                UpdateObject(context.scene.speckle_client, obj)

        context.scene.update()
        return {"FINISHED"}


class CopyStreamId(bpy.types.Operator):
    """
    Copy stream ID to clipboard
    """

    bl_idname = "speckle.stream_copy_id"
    bl_label = "Copy stream ID"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Copy stream ID to clipboard"

    def execute(self, context):
        speckle = context.scene.speckle

        if len(speckle.users) < 1:
            return {"CANCELLED"}
        user = speckle.users[int(speckle.active_user)]
        if len(user.streams) < 1:
            return {"CANCELLED"}
        stream = user.streams[user.active_stream]
        bpy.context.window_manager.clipboard = stream.id
        return {"FINISHED"}


class CopyCommitId(bpy.types.Operator):
    """
    Copy commit ID to clipboard
    """

    bl_idname = "speckle.commit_copy_id"
    bl_label = "Copy commit ID"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Copy commit ID to clipboard"

    def execute(self, context):
        speckle = context.scene.speckle

        if len(speckle.users) < 1:
            return {"CANCELLED"}
        user = speckle.users[int(speckle.active_user)]
        if len(user.streams) < 1:
            return {"CANCELLED"}
        stream = user.streams[user.active_stream]
        if len(stream.branches) < 1:
            return {"CANCELLED"}
        branch = stream.branches[int(stream.branch)]
        if len(branch.commits) < 1:
            return {"CANCELLED"}
        commit = branch.commits[int(branch.commit)]
        bpy.context.window_manager.clipboard = commit.id
        return {"FINISHED"}


class CopyBranchName(bpy.types.Operator):
    """
    Copy branch name to clipboard
    """

    bl_idname = "speckle.branch_copy_name"
    bl_label = "Copy branch name"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Copy branch name to clipboard"

    def execute(self, context):
        speckle = context.scene.speckle

        if len(speckle.users) < 1:
            return {"CANCELLED"}
        user = speckle.users[int(speckle.active_user)]
        if len(user.streams) < 1:
            return {"CANCELLED"}
        stream = user.streams[user.active_stream]
        if len(stream.branches) < 1:
            return {"CANCELLED"}
        branch = stream.branches[int(stream.branch)]
        bpy.context.window_manager.clipboard = branch.name
        return {"FINISHED"}
