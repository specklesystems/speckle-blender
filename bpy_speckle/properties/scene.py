"""
Scene properties
"""
from typing import Iterable, Optional, Tuple, Union, cast
from dataclasses import dataclass
import bpy
from bpy.props import (
    StringProperty,
    FloatProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
)

class SpeckleSceneObject(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="") # type: ignore


class SpeckleCommitObject(bpy.types.PropertyGroup):
    id: StringProperty(default="") # type: ignore
    message: StringProperty(default="") # type: ignore
    author_name: StringProperty(default="") # type: ignore
    author_id: StringProperty(default="") # type: ignore
    created_at: StringProperty(default="") # type: ignore
    source_application: StringProperty(default="") # type: ignore
    referenced_object: StringProperty(default="") # type: ignore


class SpeckleBranchObject(bpy.types.PropertyGroup):
    def get_commits(self, context):
        if self.commits != None and len(self.commits) > 0:
            COMMITS = cast(Iterable[SpeckleCommitObject], self.commits)
            return [
                (str(i), commit.id, commit.message, i)
                for i, commit in enumerate(COMMITS)
            ]
        return [("0", "<none>", "<none>", 0)]
  
    def commit_update_hook(self, context: bpy.types.Context):
        selection_state.selected_commit_id = SelectionState.get_item_id_by_index(self.commits, self.commit)

    name: StringProperty(default="main") # type: ignore
    id: StringProperty(default="") # type: ignore
    description: StringProperty(default="") # type: ignore
    commits: CollectionProperty(type=SpeckleCommitObject) # type: ignore
    commit: EnumProperty(
        name="Version",
        description="Selected model version",
        items=get_commits,
        update=commit_update_hook,
    ) # type: ignore
    
    def get_active_commit(self) -> Optional[SpeckleCommitObject]:
        selected_index = int(self.commit)
        if 0 <= selected_index < len(self.commits): 
            return self.commits[selected_index]
        return None
    
class SpeckleStreamObject(bpy.types.PropertyGroup):
    def get_branches(self, context):
        if self.branches:
            BRANCHES = cast(Iterable[SpeckleBranchObject], self.branches)
            return [
                (str(i), branch.name, branch.description, i)
                for i, branch in enumerate(BRANCHES)
                if branch.name != "globals"
            ]
        return [("0", "<none>", "<none>", 0)]
    
    def branch_update_hook(self, context: bpy.types.Context):
        selection_state.selected_branch_id = SelectionState.get_item_id_by_index(self.branches, self.branch)

    name: StringProperty(default="") # type: ignore
    description: StringProperty(default="") # type: ignore
    id: StringProperty(default="") # type: ignore
    branches: CollectionProperty(type=SpeckleBranchObject) # type: ignore
    branch: EnumProperty(
        name="Model",
        description="Selected Model",
        items=get_branches,
        update=branch_update_hook,
    ) # type: ignore

    def get_active_branch(self) -> Optional[SpeckleBranchObject]:
        selected_index = int(self.branch)
        if 0 <= selected_index < len(self.branches): 
            return self.branches[selected_index]
        return None

class SpeckleUserObject(bpy.types.PropertyGroup):
    def stream_update_hook(self, context: bpy.types.Context):
        selection_state.selected_stream_id = SelectionState.get_item_id_by_index(self.streams, self.active_stream)

    server_name: StringProperty(default="SpeckleXYZ") # type: ignore
    server_url: StringProperty(default="https://speckle.xyz") # type: ignore
    id: StringProperty(default="") # type: ignore
    name: StringProperty(default="Speckle User") # type: ignore
    email: StringProperty(default="user@speckle.xyz") # type: ignore
    company: StringProperty(default="SpeckleSystems") # type: ignore
    streams: CollectionProperty(type=SpeckleStreamObject) # type: ignore
    active_stream: IntProperty(default=0, update=stream_update_hook) # type: ignore

    def get_active_stream(self) -> Optional[SpeckleStreamObject]:
        selected_index = int(self.active_stream)
        if 0 <= selected_index < len(self.streams): 
            return self.streams[selected_index]
        return None
    

class SpeckleSceneSettings(bpy.types.PropertyGroup):
    def get_scripts(self, context):
        return [
            ("<none>", "<none>", "<none>"),
            *[(t.name, t.name, t.name) for t in bpy.data.texts],
        ]

    streams: EnumProperty(
        name="Available streams",
        description="Available streams associated with user.",
        items=[],
    ) # type: ignore

    users: CollectionProperty(type=SpeckleUserObject) # type: ignore

    def get_users(self, context):
        USERS = cast(Iterable[SpeckleUserObject], self.users)
        return [
            (str(i), f"{user.email} ({user.server_name})", user.server_url, i)
            for i, user in enumerate(USERS)
        ]

    def set_user(self, context):
        bpy.ops.speckle.load_user_streams() # type: ignore
        selection_state.selected_user_id = SelectionState.get_item_id_by_index(self.users, self.active_user)

    active_user: EnumProperty(
        items=get_users,
        name="Account",
        description="Select account",
        update=set_user,
        get=None,
        set=None,
    ) # type: ignore

    objects: CollectionProperty(type=SpeckleSceneObject) # type: ignore

    scale: FloatProperty(default=0.001) # type: ignore

    user: StringProperty(
        name="User",
        description="Current user",
        default="Speckle User",
    ) # type: ignore

    receive_script: EnumProperty(
        name="Receive script",
        description="Custom py script to execute when receiving objects. See docs for function signature.",
        items=get_scripts,
    ) # type: ignore

    send_script: EnumProperty(
        name="Send script",
        description="Custom py script to execute when sending objects. See docs for function signature",
        items=get_scripts,
    ) # type: ignore

    def get_active_user(self) -> Optional[SpeckleUserObject]:
        if not self.active_user:
            return None
        selected_index = int(self.active_user)
        if 0 <= selected_index < len(self.users):
            return self.users[selected_index]
        return None
    

    def validate_user_selection(self) -> SpeckleUserObject:
        user = self.get_active_user()
        if not user:
            raise SelectionException("No user account selected/found")
        return user
        
    def validate_stream_selection(self) -> Tuple[SpeckleUserObject, SpeckleStreamObject]:
        user = self.validate_user_selection()

        stream = user.get_active_stream()
        if not stream:
            raise SelectionException("No project selected/found")

        return (user, stream)
    
    def validate_branch_selection(self) -> Tuple[SpeckleUserObject, SpeckleStreamObject, SpeckleBranchObject]:
        (user, stream) = self.validate_stream_selection()

        branch = stream.get_active_branch()
        if not branch:
            raise SelectionException("No model selected/found")
        return (user, stream, branch)
    
    def validate_commit_selection(self) ->Tuple[SpeckleUserObject, SpeckleStreamObject, SpeckleBranchObject, SpeckleCommitObject]:
        (user, stream, branch) = self.validate_branch_selection()
        commit = branch.get_active_commit()
        if commit is None:
            raise SelectionException("No model version selected/found")
        
        return (user, stream, branch, commit)
    
class SelectionException(Exception):
    pass

def get_speckle(context: bpy.types.Context) -> SpeckleSceneSettings:
    """
    Gets the speckle scene object
    """
    return context.scene.speckle #type: ignore

@dataclass
class SelectionState:
    selected_user_id : Optional[str] = None
    selected_stream_id : Optional[str] = None
    selected_branch_id : Optional[str] = None
    selected_commit_id : Optional[str] = None

    @staticmethod
    def get_item_id_by_index(collection: bpy.types.PropertyGroup, index: Union[str, int]) -> Optional[str]:
        # print(list(collection.items()))
        selected_index = int(index)
        for index, (_, item) in enumerate(collection.items()):
            if index == selected_index:
                return item.id
        return None
    
    @staticmethod
    def get_item_index_by_id(collection: Iterable[SpeckleCommitObject], id: Optional[str]) -> Optional[str]:
        for index, item in enumerate(collection):
            if item.id == id:
                return str(index)
        return None

selection_state = SelectionState()

def restore_selection_state(speckle: SpeckleSceneSettings) -> None:
    # Restore branch selection state
    if selection_state.selected_branch_id != None:
        (active_user, active_stream) = speckle.validate_stream_selection()

        is_same_user = active_user.id == selection_state.selected_user_id
        is_same_stream = active_stream.id == selection_state.selected_stream_id
    
        if is_same_user and is_same_stream:
            if branch := SelectionState.get_item_index_by_id(active_stream.branches, selection_state.selected_branch_id):
                active_stream.branch = branch
    
    # Restore commit selection state
    if selection_state.selected_commit_id != None:
        (active_user, active_stream, active_branch) = speckle.validate_branch_selection()

        is_same_user = active_user.id == selection_state.selected_user_id
        is_same_stream = active_stream.id == selection_state.selected_stream_id
        is_same_branch = active_branch.id == selection_state.selected_branch_id

        if is_same_user and is_same_stream and is_same_branch:
            if commit := SelectionState.get_item_index_by_id(active_branch.commits, selection_state.selected_commit_id):
                active_branch.commit = commit