"""
Object operators
"""

import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy_speckle.convert.to_speckle import (
    convert_to_speckle,
    ngons_to_speckle_polylines,
)
from bpy_speckle.functions import get_scale_length, _report
from bpy_speckle.clients import speckle_clients


class UpdateObject(bpy.types.Operator):
    """
    Update local (receive) or remote (send) object depending on
    the update direction. If sending, updates the object on the
    server in-place.
    """

    bl_idname = "speckle.update_object"
    bl_label = "Update Object"
    bl_options = {"REGISTER", "UNDO"}

    client = None

    def execute(self, context):
        user = context.scene.speckle.users[int(context.scene.speckle.active_user)]
        client = speckle_clients[int(context.scene.speckle.active_user)]
        stream = user.streams[user.active_stream]

        active = context.active_object
        _report(active)

        if active is not None and active.speckle.enabled:
            if active.speckle.send_or_receive == "send" and active.speckle.stream_id:
                sstream = client.streams.get(active.speckle.stream_id)
                # res = client.StreamGetAsync(active.speckle.stream_id)['resource']
                # res = client.streams.get(active.speckle.stream_id)

                if sstream is None:
                    _report("Getting stream failed.")
                    return {"CANCELLED"}

                stream_units = "Meters"
                if sstream.baseProperties:
                    stream_units = sstream.baseProperties.units

                scale = context.scene.unit_settings.scale_length / get_scale_length(
                    stream_units
                )

                sm = convert_to_speckle(active, scale)

                _report("Updating object {}".format(sm["_id"]))
                client.objects.update(active.speckle.object_id, sm)

                return {"FINISHED"}

            return {"CANCELLED"}
        return {"CANCELLED"}


class ResetObject(bpy.types.Operator):
    """
    Reset Speckle object settings
    """

    bl_idname = "speckle.reset_object"
    bl_label = "Reset Object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):

        context.object.speckle.send_or_receive = "send"
        context.object.speckle.stream_id = ""
        context.object.speckle.object_id = ""
        context.object.speckle.enabled = False
        context.view_layer.update()

        return {"FINISHED"}


class DeleteObject(bpy.types.Operator):
    """
    Delete object from the server and update relevant stream
    """

    bl_idname = "speckle.delete_object"
    bl_label = "Delete Object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        client = speckle_clients[int(context.scene.speckle.active_user)]
        active = context.object
        if active.speckle.enabled:
            res = client.StreamGetAsync(active.speckle.stream_id)
            existing = [
                x
                for x in res["resource"]["objects"]
                if x["_id"] == active.speckle.object_id
            ]
            if existing is None:
                return {"CANCELLED"}
            new_objects = [
                x
                for x in res["resource"]["objects"]
                if x["_id"] != active.speckle.object_id
            ]

            res = client.GetLayers(active.speckle.stream_id)
            new_layers = res["resource"]["layers"]
            new_layers[-1]["objectCount"] = new_layers[-1]["objectCount"] - 1
            new_layers[-1]["topology"] = "0-%s" % new_layers[-1]["objectCount"]

            res = client.StreamUpdateAsync(
                {"objects": new_objects, "layers": new_layers}, active.speckle.stream_id
            )
            res = client.ObjectDeleteAsync(active.speckle.object_id)

            active.speckle.send_or_receive = "send"
            active.speckle.stream_id = ""
            active.speckle.object_id = ""
            active.speckle.enabled = False
            context.view_layer.update()

        return {"FINISHED"}


class UploadNgonsAsPolylines(bpy.types.Operator):
    """
    Upload mesh ngon faces as polyline outlines
    TODO: move to another category of specialized operators and fix to work with API 2.0
    """

    bl_idname = "speckle.upload_ngons_as_polylines"
    bl_label = "Upload Ngons As Polylines"
    bl_options = {"REGISTER", "UNDO"}

    clear_stream: BoolProperty(
        name="Clear stream",
        default=False,
    )

    def execute(self, context):
        active = context.active_object
        if active is not None and active.type == "MESH":

            user = context.scene.speckle.users[int(context.scene.speckle.active_user)]
            client = speckle_clients[int(context.scene.speckle.active_user)]
            stream = user.streams[user.active_stream]

            # scale = context.scene.unit_settings.scale_length / get_scale_length(
            #     stream.units
            # )
            scale = 1.0

            sp = ngons_to_speckle_polylines(active, scale)

            if sp is None:
                return {"CANCELLED"}

            placeholders = []
            for polyline in sp:

                res = client.objects.create([polyline])

                if res is None:
                    _report(client.me)
                    continue
                placeholders.extend(res)

            if not placeholders:
                return {"CANCELLED"}

                # Get list of existing objects in stream and append new object to list
            _report("Fetching stream...")
            sstream = client.streams.get(stream.id)

            if self.clear_stream:
                _report("Clearing stream...")
                sstream.objects = placeholders
                N = 0
            else:
                sstream.objects.extend(placeholders)

            N = sstream.layers[-1].objectCount
            if self.clear_stream:
                N = 0
            sstream.layers[-1].objectCount = N + len(placeholders)
            sstream.layers[-1].topology = "0-%s" % (N + len(placeholders))

            res = client.streams.update(sstream.id, sstream)

            # Update view layer
            context.view_layer.update()
            _report("Done.")

        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "clear_stream")


def get_custom_speckle_props(self, context):
    ignore = ["speckle", "cycles", "cycles_visibility"]

    active = context.active_object
    if not active:
        return []

    return [(x, "{}".format(x), "") for x in active.keys()]


class SelectIfSameCustomProperty(bpy.types.Operator):
    """
    Select scene objects if they have the same custom property
    value as the active object
    """

    bl_idname = "speckle.select_if_same_custom_props"
    bl_label = "Select Identical Custom Props"
    bl_options = {"REGISTER", "UNDO"}

    custom_prop: EnumProperty(
        name="Custom properties",
        description="Available streams associated with user.",
        items=get_custom_speckle_props,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "custom_prop")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):

        active = context.active_object
        if not active:
            return {"CANCELLED"}

        if self.custom_prop not in active.keys():
            return {"CANCELLED"}

        value = active[self.custom_prop]

        _report(
            "Looking for '{}' property with a value of '{}'.".format(
                self.custom_prop, value
            )
        )

        for obj in bpy.data.objects:

            if self.custom_prop in obj.keys() and obj[self.custom_prop] == value:
                obj.select_set(True)
            else:
                obj.select_set(False)

        return {"FINISHED"}


class SelectIfHasCustomProperty(bpy.types.Operator):
    """
    Select scene objects if they have the same custom property
    as the active object, regardless of the value
    """

    bl_idname = "speckle.select_if_has_custom_props"
    bl_label = "Select Same Custom Prop"
    bl_options = {"REGISTER", "UNDO"}

    custom_prop: EnumProperty(
        name="Custom properties",
        description="Custom properties yo",
        items=get_custom_speckle_props,
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "custom_prop")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def execute(self, context):

        active = context.active_object
        if not active:
            return {"CANCELLED"}

        if self.custom_prop not in active.keys():
            return {"CANCELLED"}

        value = active[self.custom_prop]

        _report("Looking for '{}' property.".format(self.custom_prop))

        for obj in bpy.data.objects:

            if self.custom_prop in obj.keys():
                obj.select_set(True)
            else:
                obj.select_set(False)

        return {"FINISHED"}
