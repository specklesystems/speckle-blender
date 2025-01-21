from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account


def get_account_enum_items() -> List[Tuple[str, str, str]]:
    accounts: List[Account] = get_local_accounts()
    if not accounts:
        return [("NO_ACCOUNTS", "No accounts found! Please add an account from Manager for Speckle.", "")]
    return [(acc.id, f"{acc.userInfo.name} - {acc.serverInfo.url} - {acc.userInfo.email}", "") for acc in accounts]


def get_default_account_id() -> Optional[str]:
    return next((acc.id for acc in get_local_accounts() if acc.isDefault), None)