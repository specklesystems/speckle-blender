from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts
from typing import List, Tuple
from .misc import format_relative_time

def get_projects_for_account(account_id: str) -> List[Tuple[str, str, str]]:
    """
    Fetch projects for a given account from the Speckle server.
    
    Args:
        account_id: The ID of the Speckle account to fetch projects for
        
    Returns:
        List of tuples containing (project_name, role, last_updated)
    """
    try:
        # Get the account info
        account = next((acc for acc in get_local_accounts() if acc.id == account_id), None)
        if not account:
            return []
            
        # Initialize the client
        client = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)
        
        # Fetch projects
        projects = client.active_user.get_projects(limit=10).items
        
        return [(project.name, project.role, format_relative_time(project.updatedAt) ) for project in projects]
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}\n"
        error_msg += f"Traceback:\n{''.join(traceback.format_tb(e.__traceback__))}"
        print(error_msg)  
        return []
