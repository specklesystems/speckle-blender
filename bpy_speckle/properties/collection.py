"""
Collection properties
"""

import bpy


class SpeckleCollectionSettings(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False, name="Enabled")  # type: ignore

    send_or_receive: bpy.props.EnumProperty(
        name="Mode",
        items=(
            ("send", "Send", "Send data to Speckle server."),
            ("receive", "Receive", "Receive data from Speckle server."),
        ),
    )  # type: ignore
    stream_id: bpy.props.StringProperty(default="")  # type: ignore
    name: bpy.props.StringProperty(default="")  # type: ignore
