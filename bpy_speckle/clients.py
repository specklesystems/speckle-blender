"""
Permanent handle on all user clients
"""
from specklepy.api.client import SpeckleClient


speckle_clients: list[SpeckleClient] = []
