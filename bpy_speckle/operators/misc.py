import bpy
import webbrowser
from specklepy.logging import metrics 




class OpenSpeckleGuide(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_guide"
    bl_label = "Speckle Guide"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Browse the documentation on the Speckle Guide"

    def execute(self, context):
        webbrowser.open("https://speckle.guide/user/blender.html")
        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "OpenSpeckleGuide"
            },
        )
        return {"FINISHED"}


class OpenSpeckleTutorials(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_tutorials"
    bl_label = "Tutorials Portal"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Visit our tutorials portal for learning resources"

    def execute(self, context):
        webbrowser.open("https://speckle.systems/tutorials/")
        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "OpenSpeckleTutorials"
            },
        )
        return {"FINISHED"}


class OpenSpeckleForum(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_forum"
    bl_label = "Community Forum"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Ask questions and join the discussion on our community forum"

    def execute(self, context):
        webbrowser.open("https://speckle.community/")
        metrics.track(
            "Connector Action",
            None, 
            custom_props={
                "name": "OpenSpeckleForum"
            },
        )
        return {"FINISHED"}