from specklepy.api.credentials import get_local_accounts

def get_account_enum_items() -> list[tuple[str, str, str]]:
    return [(acc.id, f"{acc.userInfo.name} - {acc.serverInfo.url} - {acc.userInfo.email}", "") for acc in get_local_accounts()]

def get_default_account_id() -> str | None:
    return next((acc.id for acc in get_local_accounts() if acc.isDefault), None)