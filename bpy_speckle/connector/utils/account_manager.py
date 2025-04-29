from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account


def get_account_enum_items() -> List[Tuple[str, str, str]]:
    """
    retrieves a list of Speckle accounts formatted for Blender enum properties
    """

    accounts: List[Account] = get_local_accounts()
    if not accounts:
        return [
            print ("No accounts found!")
            (
                "NO_ACCOUNTS",
                "No accounts found! Please add an account from Manager for Speckle.",
                "",
            )
        ]
    print ("Accounts added")
    return [
        (
            acc.id,
            f"{acc.userInfo.name} - {acc.serverInfo.url} - {acc.userInfo.email}",
            "",
        )
        for acc in accounts
    ]


def get_default_account_id() -> Optional[str]:
    """
    retrieves the ID of the default Speckle account
    """
    return next((acc.id for acc in get_local_accounts() if acc.isDefault), "NO_ACCOUNTS")


def get_server_url_by_account_id(account_id: str) -> Optional[str]:
    """
    retrieves the server URL for a given account ID
    """
    accounts: List[Account] = get_local_accounts()
    for acc in accounts:
        if acc.id == account_id:
            return acc.serverInfo.url
    return None
