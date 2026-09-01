"""The one place a ``SpeckleClient`` comes from, and the owner of what happens
when a call through one fails.

The package has exactly three failure policies, each stated once:

- **Reads** (list/lookup helpers) wear ``@api_read``: log the error, drop
  every cached client — the usual cause is a dead or stale connection — and
  return a caller-supplied fallback. The UI shows an empty list and recovers
  on the next interaction.
- **Permission checks** (``permissions.py``) return ``(False, message)`` so
  operators can put the reason in front of the user. They do not clear the
  cache: a denied permission is an answer, not a broken client.
- **Writes** (``create_project``/``create_model``) clear the cache and
  re-raise: the operator owns telling the user a mutation failed.
"""

import functools
import traceback
from typing import Dict, Optional
from urllib.parse import urlparse

from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import Account, get_local_accounts


def get_account_from_id(account_id: str) -> Optional[Account]:
    return next((acc for acc in get_local_accounts() if acc.id == account_id), None)


class SpeckleClientCache:
    def __init__(self):
        self._clients: Dict[str, SpeckleClient] = {}

    def get_client(self, account_id: str) -> SpeckleClient:
        # Check cache first
        if account_id in self._clients:
            print(f"[Cache HIT] Using cached client for account {account_id}")
            return self._clients[account_id]

        # Create new client if needed
        print(f"[Cache MISS] Creating new client for account {account_id}")
        account = get_account_from_id(account_id)
        if not account:
            raise ValueError(f"No account found for ID: {account_id}")

        url = account.serverInfo.url
        use_ssl = urlparse(url).scheme.lower() != "http"
        client = SpeckleClient(host=url, use_ssl=use_ssl)
        client.authenticate_with_account(account)
        self._clients[account_id] = client
        return client

    def clear(self) -> None:
        """Clear all cached clients."""
        print("[Cache] Clearing all cached clients")
        self._clients.clear()


# Global cache instance
client_cache = SpeckleClientCache()


def api_read(what: str, fallback):
    """Standard failure policy for read helpers — see the module docstring.

    ``fallback`` is called when callable (so mutable defaults like ``list``
    stay fresh per failure) and returned as-is otherwise.
    """

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                traceback.print_exc()
                print(f"Error {what}: {e}")
                client_cache.clear()
                return fallback() if callable(fallback) else fallback

        return wrapper

    return decorate
