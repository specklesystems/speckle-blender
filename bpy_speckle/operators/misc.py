import bpy
import webbrowser


class OpenSpeckleGuide(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_guide"
    bl_label = "Speckle Guide"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Browse the documentation on the Speckle Guide"

    def execute(self, context):
        webbrowser.open("https://speckle.guide/user/blender.html")
        return {"FINISHED"}


class OpenSpeckleTutorials(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_tutorials"
    bl_label = "Tutorials Portal"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Visit our tutorials portal for learning resources"

    def execute(self, context):
        webbrowser.open("https://speckle.systems/tutorials/")
        return {"FINISHED"}


class OpenSpeckleForum(bpy.types.Operator):
    bl_idname = "speckle.open_speckle_forum"
    bl_label = "Community Forum"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Ask questions and join the discussion on our community forum"

    def execute(self, context):
        webbrowser.open("https://speckle.community/")
        return {"FINISHED"}