from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account


def get_account_enum_items() -> List[Tuple[str, str, str]]:
    """Retrieves a list of Speckle accounts formatted for Blender enum properties.

    This function fetches all local Speckle accounts and formats them for use in Blender's
    UI dropdown menus. If no accounts are found, it returns a single entry indicating that
    no accounts are available.

    Returns:
        List[Tuple[str, str, str]]: A list of tuples where each tuple contains:
            - identifier (str): The account ID or "NO_ACCOUNTS" if none found
            - name (str): Display string with format "username - server - email" or error message
            - description (str): Empty string, reserved for future use

    Note:
        If no accounts are found, returns a single tuple with instructions for adding an account.
    """
    accounts: List[Account] = get_local_accounts()
    if not accounts:
        return [("NO_ACCOUNTS", "No accounts found! Please add an account from Manager for Speckle.", "")]
    return [(acc.id, f"{acc.userInfo.name} - {acc.serverInfo.url} - {acc.userInfo.email}", "") for acc in accounts]


def get_default_account_id() -> Optional[str]:
    """Retrieves the ID of the default Speckle account.

    This function searches through all local Speckle accounts and returns the ID
    of the account marked as default.

    Returns:
        Optional[str]: The ID of the default account if one exists, None otherwise.
    """
    return next((acc.id for acc in get_local_accounts() if acc.isDefault), "NO_ACCOUNTS")


def get_server_url_by_account_id(account_id: str) -> Optional[str]:
    """Retrieves the server URL for a given account ID.

    Args:
        account_id (str): The ID of the account.

    Returns:
        Optional[str]: The server URL if the account is found, otherwise None.
    """
    accounts: List[Account] = get_local_accounts()
    for acc in accounts:
        if acc.id == account_id:
            return acc.serverInfo.url
    return None