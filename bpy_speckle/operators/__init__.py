from .commit import DeleteCommit
from .misc import OpenSpeckleForum, OpenSpeckleGuide, OpenSpeckleTutorials
from .object import (DeleteObject, ResetObject, SelectIfHasCustomProperty,
                     SelectIfSameCustomProperty, UpdateObject,
                     UploadNgonsAsPolylines)
from .streams import (AddStreamFromURL, CopyBranchName, CopyCommitId,
                      CopyModelId, CopyStreamId, CreateStream, DeleteStream,
                      ReceiveStreamObjects, SelectOrphanObjects,
                      SendStreamObjects, ViewStreamDataApi)
from .users import LoadUsers, LoadUserStreams, ResetUsers

operator_classes = [
    LoadUsers,
    ResetUsers,
    ReceiveStreamObjects,
    SendStreamObjects,
    LoadUserStreams,
    CopyStreamId,
    CopyCommitId,
    CopyBranchName,
    CopyModelId,
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
