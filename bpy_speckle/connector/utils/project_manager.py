from specklepy.api.client import SpeckleClient
from specklepy.api.credentials import get_local_accounts
from specklepy.core.api.inputs.user_inputs import UserProjectsFilter
from typing import List, Tuple, Optional
from specklepy.core.api.credentials import Account
from .misc import format_relative_time, format_role

def get_projects_for_account(account_id: str, search: Optional[str] = None) -> List[Tuple[str, str, str, str]]:
    """Fetches projects for a given account from the Speckle server.
    
    This function retrieves a list of projects associated with a specific Speckle account.
    It authenticates with the server using the provided account credentials and optionally
    filters the results based on a search string.
    
    Args:
        account_id (str): The unique identifier of the Speckle account.
        search (Optional[str], optional): Search string to filter projects by name. Defaults to None.
    
    Returns:
        List[Tuple[str, str, str, str]]: A list of tuples where each tuple contains:
            - project_name (str): The name of the project
            - role (str): The user's formatted role in the project
            - last_updated (str): Relative time since last update
            - project_id (str): The unique identifier of the project
            
    Note:
        Returns an empty list if the account is not found or if there's an error during execution.
        Any errors encountered will be printed with their full traceback.
    """
    try:
        # Get the account info
        accounts: List[Account] = get_local_accounts()
        account: Optional[Account] = next((acc for acc in accounts if acc.id == account_id), None)
        if not account:
            return []
            
        # Initialize the client
        client = SpeckleClient(host=account.serverInfo.url)
        # Authenticate
        client.authenticate_with_account(account)
        
        # Create filter if search is provided
        filter = UserProjectsFilter(search=search) if search else None
        
        # Fetch projects
        projects = client.active_user.get_projects(limit=10, filter=filter).items
        
        return [(project.name, format_role(project.role), format_relative_time(project.updated_at), project.id) for project in projects]
        
    except Exception as e:
        import traceback
        error_msg = f"Error: {str(e)}\n"
        error_msg += f"Traceback:\n{''.join(traceback.format_tb(e.__traceback__))}"
        print(error_msg)  
        return []
