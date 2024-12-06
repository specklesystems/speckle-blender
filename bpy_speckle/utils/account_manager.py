from specklepy.api.credentials import get_local_accounts

def get_account_enum_items() -> list[tuple[str, str, str]]:
    accounts = get_local_accounts()
    if not accounts:
        return [("NO_ACCOUNTS", "No accounts found! Please add an account from Manager for Speckle.", "")]
    return [(acc.id, f"{acc.userInfo.name} - {acc.serverInfo.url} - {acc.userInfo.email}", "") for acc in get_local_accounts()]

def get_default_account_id() -> str | None:
    return next((acc.id for acc in get_local_accounts() if acc.isDefault), None)