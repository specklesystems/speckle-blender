"""
Permanent handle on all user clients
"""
from specklepy.core.api.client import SpeckleClient


speckle_clients: list[SpeckleClient] = []
