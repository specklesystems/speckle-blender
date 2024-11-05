from .addon import SpeckleAddonPreferences
from .collection import SpeckleCollectionSettings
from .object import SpeckleObjectSettings
from .scene import (SpeckleBranchObject, SpeckleCommitObject,
                    SpeckleSceneObject, SpeckleSceneSettings,
                    SpeckleStreamObject, SpeckleUserObject)

property_classes = [
    SpeckleSceneObject,
    SpeckleCommitObject,
    SpeckleBranchObject,
    SpeckleStreamObject,
    SpeckleUserObject,
    SpeckleSceneSettings,
    SpeckleObjectSettings,
    SpeckleCollectionSettings,
    SpeckleAddonPreferences,
]
