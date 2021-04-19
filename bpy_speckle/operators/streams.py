"""
Stream operators
"""

import bpy, bmesh, os
import webbrowser
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    CollectionProperty,
    EnumProperty,
)

from bpy_speckle.functions import (
    _check_speckle_client_user_stream,
    _create_stream,
    get_scale_length,
    _report,
)
from bpy_speckle.convert import to_speckle_object, get_speckle_subobjects
from bpy_speckle.convert.to_speckle import export_ngons_as_polylines

from bpy_speckle.convert import from_speckle_object
from bpy_speckle.clients import speckle_clients

from specklepy.api import operations
from specklepy.api.resources.stream import Stream
from specklepy.transports.server import ServerTransport
from specklepy.objects import Base
from specklepy.objects.geometry import *


def get_objects_recursive(base):
    objects = []
    for name in base.get_dynamic_member_names():
        if isinstance(base[name], list):
            for item in base[name]:
                if isinstance(item, Base):
                    objects.extend(get_objects_recursive(item))

    objects.append(base)
    return objects


class ReceiveStreamObjects(bpy.types.Operator):
    """
    Receive stream objects
    """

    bl_idname = "speckle.receive_stream_objects"
    bl_label = "Download Stream Objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Receive objects from active stream"

    def execute(self, context):
        bpy.context.view_layer.objects.active = None

        check = _check_speckle_client_user_stream(context.scene)
        if check is None:
            return {"CANCELLED"}

        user, bstream = check

        client = speckle_clients[int(context.scene.speckle.active_user)]

        stream = client.stream.get(id=bstream.id)
        if stream.branches.totalCount < 1:
            return {"CANCELLED"}

        if not stream.branches:
            return {"CANCELLED"}

        branch = stream.branches.items[int(bstream.branch)]

        bbranch = bstream.branches[int(bstream.branch)]

        if branch.commits.totalCount < 1:
            print("No commits found. Probably an empty stream.")
            return {"CANCELLED"}

        commit = branch.commits.items[int(bbranch.commit)]

        transport = ServerTransport(client, stream.id)
        stream_data = operations.receive(commit.referencedObject, transport)

        objects = get_objects_recursive(stream_data)

        if len(objects) < 1:
            return {"CANCELLED"}

        """
        Create or get Collection for stream objects
        """

        name = "{} [ {} @ {} ]".format(stream.name, branch.name, commit.id)

        clear_collection = True

        if name in bpy.data.collections:
            col = bpy.data.collections[name]
            if clear_collection:
                for obj in col.objects:
                    col.objects.unlink(obj)
        else:
            col = bpy.data.collections.new(name)

        existing = {}
        for obj in col.objects:
            if obj.speckle.object_id != "":
                existing[obj.speckle.object_id] = obj

        col.speckle.stream_id = stream.id
        col.speckle.name = stream.name
        col.speckle.units = stream_data.units

        """
        Set conversion scale from stream units
        """
        scale = (
            get_scale_length(stream_data.units)
            / context.scene.unit_settings.scale_length
        )

        """
        Get script from text editor for injection
        """
        func = None
        if context.scene.speckle.receive_script in bpy.data.texts:
            mod = bpy.data.texts[context.scene.speckle.receive_script].as_module()
            if hasattr(mod, "execute"):
                func = mod.execute

        """
        Iterate through retrieved resources
        """
        for obj in objects:
            new_objects = [from_speckle_object(obj, scale)]

            if hasattr(obj, "properties") and obj.properties is not None:
                new_objects.extend(
                    get_speckle_subobjects(obj.properties, scale, obj.id)
                )
            elif isinstance(obj, dict) and "properties" in obj.keys():
                new_objects.extend(
                    get_speckle_subobjects(obj["properties"], scale, obj["id"])
                )

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
                    new_object = func(context.scene, new_object)

                if (
                    new_object is None
                ):  # Make sure that the injected function returned an object
                    new_obj = new_object
                    _report("Script '{}' returned None.".format(func.__module__))
                    continue

                new_object.speckle.stream_id = stream.id
                new_object.speckle.send_or_receive = "receive"

                if new_object.speckle.object_id in existing.keys():
                    name = existing[new_object.speckle.object_id].name
                    existing[new_object.speckle.object_id].name = name + "__deleted"
                    new_object.name = name
                    col.objects.unlink(existing[new_object.speckle.object_id])

                if new_object.name not in col.objects:
                    col.objects.link(new_object)

        if col.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(col)

        bpy.context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class SendStreamObjects(bpy.types.Operator):
    """
    Send stream objects
    """

    bl_idname = "speckle.send_stream_objects"
    bl_label = "Send stream objects"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Send selected objects to active stream"

    commit_message: StringProperty(
        name="Message",
        default="Pushed elements from Blender.",
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "commit_message")

    def invoke(self, context, event):
        wm = context.window_manager
        if len(context.scene.speckle.users) > 0:
            N = len(context.selected_objects)
            if N == 1:
                self.commit_message = "Pushed {} element from Blender.".format(N)
            else:
                self.commit_message = "Pushed {} elements from Blender.".format(N)
            return wm.invoke_props_dialog(self)

        return {"CANCELLED"}

    def execute(self, context):

        selected = context.selected_objects

        if len(selected) < 1:
            return {"CANCELLED"}

        check = _check_speckle_client_user_stream(context.scene)
        if check is None:
            return {"CANCELLED"}

        user, bstream = check
        stream = user.streams[user.active_stream]
        branch = stream.branches[int(stream.branch)]

        client = speckle_clients[int(context.scene.speckle.active_user)]

        scale = context.scene.unit_settings.scale_length / get_scale_length(
            stream.units.lower()
        )

        """
        Get script from text editor for injection
        """
        func = None
        if context.scene.speckle.send_script in bpy.data.texts:
            mod = bpy.data.texts[context.scene.speckle.send_script].as_module()
            if hasattr(mod, "execute"):
                func = mod.execute

        export = []

        for obj in selected:

            # if obj.type != 'MESH':
            #     continue

            new_object = obj

            """
            Run injected function
            """
            if func:
                new_object = func(context.scene, obj)

                if (
                    new_object is None
                ):  # Make sure that the injected function returned an object
                    new_obj = obj
                    _report("Script '{}' returned None.".format(func.__module__))
                    continue

            _report("Converting {}".format(obj.name))

            ngons = obj.get("speckle_ngons_as_polylines", False)

            if ngons:
                export.extend(export_ngons_as_polylines(obj, scale))
            else:
                export.extend(to_speckle_object(obj, scale))

        # _report(export)

        base = Base(Default=export)
        transport = ServerTransport(client, stream.id)

        obj_id = operations.send(base, [transport])
        commit_id = client.commit.create(
            stream.id,
            obj_id,
            branch.name,
            message=self.commit_message,
        )

        bpy.ops.speckle.load_user_streams()

        context.view_layer.update()

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ViewStreamDataApi(bpy.types.Operator):
    bl_idname = "speckle.view_stream_data_api"
    bl_label = "View Stream Data (API)"
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


class CreateStream(bpy.types.Operator):
    """
    Create new stream
    """

    bl_idname = "speckle.create_stream"
    bl_label = "Create stream"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Create new stream"

    stream_name: StringProperty(name="Stream name", default="SpeckleStream")
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

        new_stream_id = client.stream.create(
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

        speckle = context.scene.speckle

        check = _check_speckle_client_user_stream(context.scene)
        if check is None:
            return {"CANCELLED"}

        user, stream = check
        client = speckle_clients[int(context.scene.speckle.active_user)]

        deleted = client.stream.delete(id=stream.id)

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
        else:
            user = speckle.users[int(speckle.active_user)]
            if len(user.streams) < 1:
                return {"CANCELLED"}
            else:
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
        else:
            user = speckle.users[int(speckle.active_user)]
            if len(user.streams) < 1:
                return {"CANCELLED"}
            else:
                stream = user.streams[user.active_stream]
                if len(stream.branches) < 1:
                    return {"CANCELLED"}
                else:
                    branch = stream.branches[int(stream.branch)]
                    if len(branch.commits) < 1:
                        return {"CANCELLED"}
                    else:
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
        else:
            user = speckle.users[int(speckle.active_user)]
            if len(user.streams) < 1:
                return {"CANCELLED"}
            else:
                stream = user.streams[user.active_stream]
                if len(stream.branches) < 1:
                    return {"CANCELLED"}
                else:
                    branch = stream.branches[int(stream.branch)]
                    bpy.context.window_manager.clipboard = branch.name
                return {"FINISHED"}
