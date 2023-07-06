from .users import LoadUsers, LoadUserStreams, ResetUsers
from .object import (
    UpdateObject,
    ResetObject,
    DeleteObject,
    UploadNgonsAsPolylines,
    SelectIfSameCustomProperty,
    SelectIfHasCustomProperty,
)
from .streams import (
    ReceiveStreamObjects,
    SendStreamObjects,
    ViewStreamDataApi,
    DeleteStream,
    SelectOrphanObjects,
)
from .streams import (
    AddStreamFromURL,
    CreateStream,
    CopyStreamId,
    CopyCommitId,
    CopyBranchName,
)
from .commit import DeleteCommit
from .misc import OpenSpeckleGuide, OpenSpeckleTutorials, OpenSpeckleForum

operator_classes = [
    LoadUsers,
    ResetUsers,
    ReceiveStreamObjects,
    SendStreamObjects,
    LoadUserStreams,
    CopyStreamId,
    CopyCommitId,
    CopyBranchName,
]

operator_classes.extend([DeleteCommit])

operator_classes.extend(
    [
        UpdateObject,
        ResetObject,
        DeleteObject,
        UploadNgonsAsPolylines,
        SelectIfSameCustomProperty,
        SelectIfHasCustomProperty,
    ]
)

operator_classes.extend(
    [
        ViewStreamDataApi,
        DeleteStream,
        SelectOrphanObjects,
        AddStreamFromURL,
        CreateStream,
        OpenSpeckleGuide,
        OpenSpeckleTutorials,
        OpenSpeckleForum,
    ]
)
