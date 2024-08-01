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

from bpy_speckle.clients import speckle_clients
from specklepy.core.api.models import Stream

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
        print("commit_update_hook")
        selection_state.selected_commit_id = SelectionState.get_item_id_by_index(self.commits, self.commit)
        selection_state.selected_branch_id = self.id
        print(f"commit_update_hook: {selection_state.selected_commit_id=}, {selection_state.selected_branch_id=}")

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
    def load_stream_branches(self, sstream: Stream):
        self.branches.clear()
        # branches = [branch for branch in stream.branches.items if branch.name != "globals"]
        for b in sstream.branches.items:
            branch = cast(SpeckleBranchObject, self.branches.add())
            branch.name = b.name
            branch.id = b.id
            branch.description = b.description or ""

            if not b.commits:
                continue

            for c in b.commits.items:
                commit: SpeckleCommitObject = branch.commits.add()
                commit.id = commit.name = c.id
                commit.message = c.message or ""
                commit.author_name = c.authorName
                commit.author_id = c.authorId
                commit.created_at = c.createdAt.strftime("%Y-%m-%d %H:%M:%S.%f%Z") if c.createdAt else ""
                commit.source_application = str(c.sourceApplication)
                commit.referenced_object = c.referencedObject

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
        print("branch_update_hook")
        selection_state.selected_branch_id = SelectionState.get_item_id_by_index(self.branches, self.branch)
        selection_state.selected_stream_id = self.id
        print(f"branch_update_hook: {selection_state.selected_branch_id=}, {selection_state.selected_stream_id=}")

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
    def fetch_stream_branches(self, context: bpy.types.Context, stream: SpeckleStreamObject):
        speckle = context.scene.speckle
        client = speckle_clients[int(speckle.active_user)]
        sstream = client.stream.get(id=stream.id, branch_limit=100, commit_limit=10) # TODO: refactor magic numbers
        stream.load_stream_branches(sstream)

    def stream_update_hook(self, context: bpy.types.Context):
        print("stream_update_hook")
        stream = SelectionState.get_item_by_index(self.streams, self.active_stream)
        selection_state.selected_stream_id = stream.id
        selection_state.selected_user_id = self.id
        print(f"stream_update_hook: {selection_state.selected_stream_id=}, {selection_state.selected_user_id=}")
        if len(stream.branches) == 0: # do not reload on selection, same as the old behavior 
            self.fetch_stream_branches(context, stream)

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
        if self.active_user is None:
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
        if item := SelectionState.get_item_by_index(collection, index):
            return item.id
        return None
    
    @staticmethod
    def get_item_by_index(collection: bpy.types.PropertyGroup, index: Union[str, int]) -> Optional[bpy.types.PropertyGroup]:
        items = collection.values()
        i = int(index)
        if 0 <= i <= len(items):
            return items[i]
        return None
    
    @staticmethod
    def get_item_index_by_id(collection: Iterable[SpeckleCommitObject], id: Optional[str]) -> Optional[str]:
        for index, item in enumerate(collection):
            if item.id == id:
                return str(index)
        return None

selection_state = SelectionState()

def restore_selection_state(speckle: SpeckleSceneSettings) -> None:
    print("restore_selection_state")
    # Restore branch selection state
    if selection_state.selected_branch_id != None:
        print("restore_selection_state: branch")
        (active_user, active_stream) = speckle.validate_stream_selection()
        print(f"restore_selection_state: {active_user.id=}, {active_stream.id=}")
        print(f"restore_selection_state: {selection_state.selected_user_id=}, {selection_state.selected_stream_id=}, {selection_state.selected_branch_id=}, {selection_state.selected_commit_id=}")

        is_same_user = active_user.id == selection_state.selected_user_id
    
        if is_same_user:
            print("restore_selection_state: branch: same user")
            active_user.active_stream = int(SelectionState.get_item_index_by_id(active_user.streams, selection_state.selected_stream_id))
            active_stream = SelectionState.get_item_by_index(active_user.streams, active_user.active_stream)
            if branch := SelectionState.get_item_index_by_id(active_stream.branches, selection_state.selected_branch_id):
                print("restore_selection_state: found branch")
                active_stream.branch = branch
    
    # Restore commit selection state
    if selection_state.selected_commit_id != None:
        print("restore_selection_state: commit")
        (active_user, active_stream) = speckle.validate_stream_selection()

        active_branch = active_stream.get_active_branch()

        if active_branch is None:
            active_branch = active_stream.branches[0]
        print(f"restore_selection_state: {active_user.id=}, {active_stream.id=}, {active_branch.id=}")
        print(f"restore_selection_state: {selection_state.selected_user_id=}, {selection_state.selected_stream_id=}, {selection_state.selected_branch_id=}, {selection_state.selected_commit_id=}")

        is_same_user = active_user.id == selection_state.selected_user_id
        is_same_stream = active_stream.id == selection_state.selected_stream_id
        is_same_branch = active_branch.id == selection_state.selected_branch_id

        if is_same_user and is_same_stream and is_same_branch:
            if commit := SelectionState.get_item_index_by_id(active_branch.commits, selection_state.selected_commit_id):
                active_branch.commit = commit

    print("restore_selection_state: save")
    (active_user, active_stream, active_branch, active_commit) = speckle.validate_commit_selection()
    # selection_state.selected_user_id = active_user.id
    # selection_state.selected_stream_id = active_stream.id
    selection_state.selected_branch_id = active_branch.id
    selection_state.selected_commit_id = active_commit.id
    print("restore_selection_state: done")