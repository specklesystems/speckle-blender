import webbrowser

import bpy
from specklepy.logging import metrics


class OpenSpeckleGuide(bpy.types.Operator):
    _guide_url = "https://speckle.guide/user/blender.html"

    bl_idname = "speckle.open_speckle_guide"
    bl_label = "Speckle Docs"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = f"Browse the documentation on the Speckle Guide ({_guide_url})"

    def execute(self, context):
        webbrowser.open(self._guide_url)
        metrics.track(
            "Connector Action",
            None,
            custom_props={"name": "OpenSpeckleGuide"},
        )
        return {"FINISHED"}


class OpenSpeckleTutorials(bpy.types.Operator):
    _tutorials_url = "https://speckle.systems/tutorials/"

    bl_idname = "speckle.open_speckle_tutorials"
    bl_label = "Tutorials Portal"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        f"Visit our tutorials portal for learning resources ({_tutorials_url})"
    )

    def execute(self, context):
        webbrowser.open(self._tutorials_url)
        metrics.track(
            "Connector Action",
            None,
            custom_props={"name": "OpenSpeckleTutorials"},
        )
        return {"FINISHED"}


class OpenSpeckleForum(bpy.types.Operator):
    _forum_url = "https://speckle.community/"

    bl_idname = "speckle.open_speckle_forum"
    bl_label = "Community Forum"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = (
        f"Ask questions and join the discussion on our community forum ({_forum_url})"
    )

    def execute(self, context):
        webbrowser.open(self._forum_url)
        metrics.track(
            "Connector Action",
            None,
            custom_props={"name": "OpenSpeckleForum"},
        )
        return {"FINISHED"}
