"""
Stream operators
"""
from math import radians
from typing import Callable, Dict, Optional, Tuple, Union, cast
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
from deprecated import deprecated
from bpy_speckle.blender_commit_object_builder import BlenderCommitObjectBuilder
from bpy_speckle.convert.to_native import (
    can_convert_to_native,
    collection_to_native,
    convert_to_native,
    set_convert_instances_as,
)
from bpy_speckle.convert.to_speckle import (
    convert_to_speckle,
)
from bpy_speckle.functions import (
    get_default_traversal_func,
    _report,
    get_scale_length,
)
from bpy_speckle.clients import speckle_clients
from bpy_speckle.operators.users import LoadUserStreams, add_user_stream
from bpy_speckle.properties.scene import SpeckleSceneSettings, SpeckleStreamObject, SpeckleUserObject, get_speckle
from bpy_speckle.convert.util import ConversionSkippedException, add_to_hierarchy
from specklepy.core.api.models import Commit
from specklepy.core.api import operations, host_applications
from specklepy.core.api.wrapper import StreamWrapper
from specklepy.core.api.resources.stream import Stream
from specklepy.transports.server import ServerTransport
from specklepy.objects import Base
from specklepy.objects.other import Collection as SCollection
from specklepy.logging.exceptions import SpeckleException
from specklepy.logging import metrics

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
            objectCallback = mod.execute_for_each #type: ignore
        elif hasattr(mod, "execute"): 
            objectCallback = lambda c, o, _ : mod.execute(c.scene, o) #type: ignore

        if hasattr(mod, "execute_for_all"):
            receiveCompleteCallback = mod.execute_for_all #type: ignore

    return (objectCallback, receiveCompleteCallback)

#RECEIVE_MODES = [#TODO: modes
#    ("create", "Create", "Add new geometry, without removing any existing objects"),
#    ("replace", "Replace", "Replace objects from previous receive operations from the same stream"),
#    #("update","Update", "") #TODO: update mode!
#]

INSTANCES_SETTINGS = [
    ("collection_instance", "Collection Instance", "Receive Instances as Collection Instances"),
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

    clean_meshes: BoolProperty(name="Clean Meshes", default=False) # type: ignore 

    #receive_mode: EnumProperty(items=RECEIVE_MODES, name="Receive Type", default="replace", description="The behaviour of the receive operation")
    receive_instances_as: EnumProperty(items=INSTANCES_SETTINGS, name="Receive Instances As", default="collection_instance", description="How to receive speckle Instances") # type: ignore 
    

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
        bpy.context.view_layer.objects.active = None # type: ignore 

    def execute(self, context):
        self.receive(context)
        return {"FINISHED"}

    def receive(self, context: Context) -> None:
        bpy.context.view_layer.objects.active = None # type: ignore 

        speckle = get_speckle(context)
        
        (user, stream, branch, commit) = speckle.validate_commit_selection()
        
        client = speckle_clients[int(speckle.active_user)]

        transport = ServerTransport(stream.id, client)
        
        # Fetch commit data
        commit_object = operations.receive(commit.referenced_object, transport)
        client.commit.received(
            stream.id,
            commit.id,
            source_application="blender",
            message="received commit from Speckle Blender",
        )

        metrics.track(
            metrics.RECEIVE,
            getattr(transport, "account", None), 
            custom_props={
                "sourceHostApp": host_applications.get_host_app_from_string(commit.source_application).slug,
                "sourceHostAppVersion": commit.source_application,
                "isMultiplayer": commit.author_id != user.id,
                #"connector_version": "unknown", #TODO
            },
        )


        # Convert received data
        context.window_manager.progress_begin(0, commit_object.totalChildrenCount or 1)

        set_convert_instances_as(self.receive_instances_as) #HACK: we need a better way to pass settings down to the converter

        traversalFunc = get_default_traversal_func(can_convert_to_native)
        converted_objects: Dict[str, Union[Object, Collection]] = {}
        converted_count: int = 0
        (object_converted_callback, on_complete_callback) = get_receive_funcs(speckle)

        # older commits will have a non-collection root object
        # for the sake of consistent behaviour, we will wrap any non-collection commit objects in a collection
        if not isinstance(commit_object, SCollection):
            dummy_commit_object = SCollection()
            dummy_commit_object.elements = [commit_object]
            dummy_commit_object.name = getattr(commit_object, "name", None)
            dummy_commit_object.id = dummy_commit_object.get_id()
            commit_object = dummy_commit_object

        # ensure commit object has a name if not already
        if not commit_object.name:
            commit_object.name = "{} [ {} @ {} ]".format(stream.name, branch.name, commit.id) # Matches Rhino "Create" naming

        for item in traversalFunc.traverse(commit_object):
            
            current: Base = item.current

            if can_convert_to_native(current) or isinstance(current, SCollection):
                try:
                    if not current or not current.id:
                        raise Exception(f"{current} was an invalid speckle object")

                    #Convert the object!
                    converted_data_type: str
                    converted: Union[Object, Collection, None]
                    if isinstance(current, SCollection):
                        if(current.collectionType == "Scene Collection"): raise ConversionSkippedException()
                        converted = collection_to_native(current)
                        converted_data_type = "COLLECTION"
                    else:
                        converted = convert_to_native(current)
                        converted_data_type = "COLLECTION_INSTANCE" if converted.instance_collection else str(converted.type)
                        
                        #Run the user specified callback function (AKA receive script)
                        if object_converted_callback:
                            converted = object_converted_callback(context, converted, current)
                    
                    if converted is None:
                        raise Exception("Conversion returned None")
                        
                    converted_objects[current.id] = converted

                    add_to_hierarchy(converted, item, converted_objects, True)

                    _report(f"Successfully converted {type(current).__name__} {current.id} as '{converted_data_type}'")
                except ConversionSkippedException as ex:
                    _report(f"Skipped converting {type(current).__name__} {current.id}: {ex}")
                except Exception as ex:
                    _report(f"Failed to converted {type(current).__name__} {current.id}: {ex}")

            converted_count += 1
            context.window_manager.progress_update(converted_count) #NOTE: We don't expect to ever reach 100% since not every object will be traversed


        context.window_manager.progress_end()

        if self.clean_meshes:
            objects = {k: v for k, v in converted_objects.items() if isinstance(v, Object)}
            self.clean_converted_meshes(context, objects)

        if on_complete_callback:
            on_complete_callback(context, converted_objects)



class SendStreamObjects(bpy.types.Operator):
    """
    Send stream objects
    """

    bl_idname = "speckle.send_stream_objects"
    bl_label = "Send stream objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Send selected objects to active stream"

    apply_modifiers: BoolProperty(name="Apply modifiers", default=True) # type: ignore 
    commit_message: StringProperty(
        name="Message",
        default="Pushed elements from Blender.",
    ) # type: ignore 

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "commit_message")
        col.prop(self, "apply_modifiers")

    def invoke(self, context, event):
        wm = context.window_manager
        speckle = get_speckle(context)
        if len(speckle.users) <= 0:
            _report("No user accounts")
            return {"CANCELLED"}
        
        N = len(context.selected_objects)
        if N == 1:
            self.commit_message = f"Pushed {N} element from Blender."
        else:
            self.commit_message = f"Pushed {N} elements from Blender."
        return wm.invoke_props_dialog(self)


    def execute(self, context):
        self.send(context)
        return {"FINISHED"}

    def send(self, context: Context) -> None:

        selected = context.selected_objects
        if len(selected) < 1:
            raise Exception("No objects are selected, sending canceled")

        speckle = get_speckle(context)
        (user, stream, branch) = speckle.validate_branch_selection()

        client = speckle_clients[int(speckle.active_user)]

        units = "m" if bpy.context.scene.unit_settings.system == "METRIC" else "ft"

        units_scale = context.scene.unit_settings.scale_length / get_scale_length(units)

        # Get script from text editor for injection
        func = None
        if speckle.send_script in bpy.data.texts:
            mod = bpy.data.texts[speckle.send_script].as_module()
            if hasattr(mod, "execute"):
                func = mod.execute #type: ignore

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
                    units_scale,
                    units,
                    depsgraph
                )

                if not converted:
                    raise Exception("Converter returned None")

                commit_builder.include_object(converted, obj)

                _report(f"Successfully converted '{obj.name_full}' as '{converted.speckle_type}'")
            except ConversionSkippedException as ex:
                _report(f"Skipped converting '{obj.name_full}': '{ex}'")
            except Exception as ex:
                _report(f"Failed to converted '{obj.name_full}': '{ex}'")
                
            num_converted += 1
            context.window_manager.progress_update(num_converted)

        context.window_manager.progress_end()

        commit_object = commit_builder.ensure_collection(context.scene.collection)
        commit_builder.build_commit_object(commit_object)

        metrics.track(
            metrics.SEND,
            client.account, 
            custom_props={
                "branches": len(stream.branches),
                #"collaborators": 0, #TODO: 
                "isMain": branch.name == "main",
            },
        )
    
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

        if client.account.serverInfo.frontend2:
            sent_url = f"{user.server_url}/projects/{stream.id}/models/{branch.id}@{COMMIT_ID}"
        else:
            sent_url = f"{user.server_url}/streams/{stream.id}/commits/{COMMIT_ID}"

        _report(f"Commit Created {sent_url}")

        bpy.ops.speckle.load_user_streams() # refresh loaded commits
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()



class ViewStreamDataApi(bpy.types.Operator):
    bl_idname = "speckle.view_stream_data_api"
    bl_label = "Open Stream in Web"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "View the stream in the web browser"

    def execute(self, context):
        self.view_stream_data_api(context)
        return {"FINISHED"}

    def view_stream_data_api(self, context: Context) -> None:
        speckle = get_speckle(context)

        (user, stream) = speckle.validate_stream_selection()

        client = speckle_clients[int(speckle.active_user)]
        if client.account.serverInfo.frontend2:
            stream_url = f"{user.server_url}/projects/{stream.id}"
        else:
            stream_url= f"{user.server_url}/streams/{stream.id}"

        if not webbrowser.open(stream_url, new=2):
            raise Exception("Failed to open stream in browser")
        
        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "view_stream_data_api"
            },
        )


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
    ) # type: ignore 

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "stream_url")

    def invoke(self, context, event):
        wm = context.window_manager
        speckle = get_speckle(context)
        if len(speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        self.add_stream_from_url(context)
        return {"FINISHED"}

    @staticmethod
    def _get_or_add_stream(user : SpeckleUserObject, stream : Stream) -> Tuple[int, SpeckleStreamObject]:
        index, b_stream = next(
            ((i, cast(SpeckleStreamObject, s)) for i, s in enumerate(user.streams) if s.id == stream.id),
            (None, None),
        )

        if index is not None:
            assert(b_stream)
            return (index, b_stream)
        
        add_user_stream(user, stream)
        return next(
            (i, cast(SpeckleStreamObject, s)) for i, s in enumerate(user.streams) if s.id == stream.id
        )
            

    def add_stream_from_url(self, context: Context) -> None:
        speckle = get_speckle(context)

        wrapper = StreamWrapper(self.stream_url)
        user_index = next(
            (i for i, u in enumerate(speckle.users) if wrapper.host in u.server_url),
            None,
        )
        if user_index is None:
            raise Exception(f"No user account credentials for {wrapper.host}, have you added your account in Manager?")
        
        speckle.active_user = str(user_index)
        user = cast(SpeckleUserObject, speckle.users[user_index])

        client = speckle_clients[user_index]
        stream = client.stream.get(wrapper.stream_id, branch_limit=LoadUserStreams.branch_limit, commit_limit=LoadUserStreams.commits_limit)
        if not isinstance(stream, Stream):
            raise SpeckleException(f"Could not get the requested stream {wrapper.stream_id}")

        (index, b_stream) = self._get_or_add_stream(user, stream)
        user.active_stream = index

        _report(f"Selecting stream at index {index} ({b_stream.id} - {b_stream.name})")

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
        
        metrics.track(
            "Connector Action",
            client.account, 
            custom_props={
                "name": "add_stream_from_url"
            },
        )


class CreateStream(bpy.types.Operator):
    """
    Create new stream
    """

    bl_idname = "speckle.create_stream"
    bl_label = "Create stream"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Create new stream"

    stream_name: StringProperty(name="Stream name") # type: ignore 
    stream_description: StringProperty(
        name="Stream description", default="This is a Blender stream."
    ) # type: ignore 

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "stream_name")
        col.prop(self, "stream_description")

    def invoke(self, context, event):
        wm = context.window_manager
        speckle = get_speckle(context)
        if len(speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        self.create_stream(context)
        return {"FINISHED"}
        
    def create_stream(self, context: Context) -> None:
        speckle = get_speckle(context)

        user = speckle.validate_user_selection()

        client = speckle_clients[int(speckle.active_user)]

        client.stream.create(
            name=self.stream_name, 
            description=self.stream_description, 
            is_public=True
        )

        bpy.ops.speckle.load_user_streams()
        user.active_stream = user.streams.find(self.stream_name)

        # Update view layer
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        
        metrics.track(
            "Connector Action",
            client.account, 
            custom_props={
                "name": "create_stream"
            },
        )


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
    ) # type: ignore 

    delete_collection: BoolProperty(name="Delete collection", default=False) # type: ignore 

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "are_you_sure")
        col.prop(self, "delete_collection")

    def invoke(self, context, event):
        wm = context.window_manager
        speckle = get_speckle(context)
        if len(speckle.users) > 0:
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):
        if not self.are_you_sure:
            _report(f"Cancelled by user - are_you_sure was {self.are_you_sure}")
            return {"CANCELLED"}
        self.are_you_sure = False

        self.delete_stream(context, self.delete_collection)
        return {"FINISHED"}

    @staticmethod
    def delete_stream(context: Context, delete_collection: bool) -> None:
        speckle = get_speckle(context)
        (_, stream) = speckle.validate_stream_selection()

        client = speckle_clients[int(speckle.active_user)]

        client.stream.delete(id=stream.id)

        if delete_collection:
            # This may not work anymore since we changed the collection naming...
            col_name = "SpeckleStream_{}_{}".format(stream.name, stream.id)
            if col_name in bpy.data.collections:
                collection = bpy.data.collections[col_name]
                bpy.data.collections.remove(collection)

        bpy.ops.speckle.load_user_streams()
        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()

        metrics.track(
            "Connector Action",
            client.account, 
            custom_props={
                "name": "delete_stream"
            },
        )

@deprecated
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

        metrics.track(
            "Connector Action", 
            custom_props={
                "name": "SelectOrphanObjects"
            },
        )

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
        self.copy_stream_id(context)
        return {"FINISHED"}
        
    def copy_stream_id(self, context) -> None:
        speckle = get_speckle(context)

        (_, stream) = speckle.validate_stream_selection()
        bpy.context.window_manager.clipboard = stream.id

        metrics.track(
            "Connector Action",
            custom_props={
                "name": "copy_stream_id"
            },
        )

class CopyCommitId(bpy.types.Operator):
    """
    Copy commit ID to clipboard
    """

    bl_idname = "speckle.commit_copy_id"
    bl_label = "Copy commit ID"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Copy commit ID to clipboard"

    def execute(self, context):
        self.copy_commit_id(context)
        return {"FINISHED"}

        
    def copy_commit_id(self, context) -> None:
        speckle = get_speckle(context)

        (_, _, _, commit) = speckle.validate_commit_selection()
        bpy.context.window_manager.clipboard = commit.id

        metrics.track(
            "Connector Action",
            custom_props={
                "name": "copy_commit_id"
            },
        )



class CopyBranchName(bpy.types.Operator):
    """
    Copy branch name to clipboard
    """

    bl_idname = "speckle.branch_copy_name"
    bl_label = "Copy branch name"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Copy branch name to clipboard"

    def execute(self, context):
        self.copy_branch_id(context)
        return {"FINISHED"}

        
    def copy_branch_id(self, context) -> None:
        speckle = get_speckle(context)

        (_, _, branch) = speckle.validate_branch_selection()

        bpy.context.window_manager.clipboard = branch.name

        metrics.track(
            "Connector Action",
            custom_props={
                "name": "copy_branch_id"
            },
        )
