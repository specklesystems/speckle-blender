"""
Machine-wide connector preferences, shared with the C# (DUI3) connectors.

The DUI3 connectors persist the user's last selected account in a SQLite
database called `DUI3Config` in the user's Speckle folder (next to the
Accounts db), one JSON blob per key:

    objects[hash TEXT PRIMARY KEY, content TEXT]
    'accounts' -> {"userSelectedAccountId": "..."}

Reading and writing that same row is what makes the account selection follow
the user across Rhino/Revit/Archicad and Blender, and survive restarts.
All failures are soft: a missing or locked db falls back to the default
account rather than breaking the UI.
"""

import json
import os
import sqlite3
from typing import Optional

from specklepy.core.helpers.speckle_path_provider import user_speckle_folder_path

_ACCOUNTS_KEY = "accounts"
_USER_SELECTED_ACCOUNT_FIELD = "userSelectedAccountId"


def _db_path() -> str:
    return str(user_speckle_folder_path() / "DUI3Config.db")


def get_user_selected_account_id() -> Optional[str]:
    """Read the machine-wide last selected account id, or None."""
    db_path = _db_path()
    if not os.path.exists(db_path):
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT content FROM objects WHERE hash = ?", (_ACCOUNTS_KEY,)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row[0]).get(_USER_SELECTED_ACCOUNT_FIELD)
        return value if isinstance(value, str) and value else None
    except Exception as e:
        print(f"[Speckle] Could not read selected account from DUI3Config: {e}")
        return None


def set_user_selected_account_id(account_id: str) -> None:
    """Persist the selected account id for all connectors on this machine."""
    content = json.dumps({_USER_SELECTED_ACCOUNT_FIELD: account_id})
    try:
        with sqlite3.connect(_db_path()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS objects("
                "hash TEXT PRIMARY KEY, content TEXT) WITHOUT ROWID"
            )
            connection.execute(
                "INSERT OR REPLACE INTO objects (hash, content) VALUES (?, ?)",
                (_ACCOUNTS_KEY, content),
            )
    except Exception as e:
        print(f"[Speckle] Could not persist selected account to DUI3Config: {e}")
