"""
Object properties
"""
import bpy


class SpeckleObjectSettings(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False, name="Enabled")

    send_or_receive: bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("send", "Send", "Send data to Speckle server."),
            ("receive", "Receive", "Receive data from Speckle server."),
        ),
    ) # type: ignore
    stream_id: bpy.props.StringProperty(default="") # type: ignore
    object_id: bpy.props.StringProperty(default="") # type: ignore
