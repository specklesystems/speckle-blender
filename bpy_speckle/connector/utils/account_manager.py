import bpy
from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account


class speckle_account(bpy.types.PropertyGroup):
    id:bpy.props.StringProperty() # type: ignore
    user_name: bpy.props.StringProperty() # type: ignore
    server_url: bpy.props.StringProperty() # type: ignore
    user_email: bpy.props.StringProperty() # type: ignore

def get_account_enum_items() -> List[Tuple[str, str, str, str]]:
    accounts: List[Account] = get_local_accounts()
    if not accounts:
        print ("No accounts found!")
        return [("NO_ACCOUNTS", "No accounts found!", "", "")]
    print ("Accounts added")
    speckle_accounts = []
    for acc in accounts:
        speckle_accounts.append((acc.id, acc.userInfo.name, acc.serverInfo.url, acc.userInfo.email))
    return speckle_accounts


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
