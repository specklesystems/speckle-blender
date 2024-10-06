from specklepy.logging.exceptions import SpeckleException
from specklepy.api.credentials import get_local_accounts, get_default_account

class AccountBinding:
    # Fetch accounts from local
    @staticmethod
    def get_account_enum_items():
        try:
            accounts = get_local_accounts()
            return [
                (
                account.id,
                f"{account.userInfo.name} - {account.userInfo.email} - {account.serverInfo.url}", 
                f"{account.userInfo.name} - {account.userInfo.email} - {account.serverInfo.url}"
                )
                for account in accounts
            ]
        except SpeckleException as e:
            print(f"Error fetching Speckle accounts: {e}")
            return [("", "No accounts found", "")]

    # Set default account
    @staticmethod
    def get_default_account_id():
        default_account = get_default_account()
        return default_account.id
