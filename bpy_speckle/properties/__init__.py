from .scene import SpeckleSceneSettings, SpeckleSceneObject, SpeckleUserObject, SpeckleStreamObject, SpeckleBranchObject, SpeckleCommitObject
from .object import SpeckleObjectSettings
from .collection import SpeckleCollectionSettings
from .addon import SpeckleAddonPreferences

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