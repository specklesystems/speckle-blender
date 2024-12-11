from .commit import DeleteCommit
from .misc import OpenSpeckleForum, OpenSpeckleGuide, OpenSpeckleTutorials
from .streams import (
    AddStreamFromURL,
    CopyCommitId,
    CopyModelId,
    CopyStreamId,
    CreateStream,
    ReceiveStreamObjects,
    SendStreamObjects,
    ViewStreamDataApi,
)
from .users import LoadUsers, LoadUserStreams, ResetUsers

operator_classes = [
    LoadUsers,
    ResetUsers,
    ReceiveStreamObjects,
    SendStreamObjects,
    LoadUserStreams,
    CopyStreamId,
    CopyCommitId,
    CopyModelId,
]

operator_classes.extend([DeleteCommit])

operator_classes.extend(
    [
        ViewStreamDataApi,
        AddStreamFromURL,
        CreateStream,
        OpenSpeckleGuide,
        OpenSpeckleTutorials,
        OpenSpeckleForum,
    ]
)
