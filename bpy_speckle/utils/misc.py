from datetime import datetime, timezone, timedelta
from typing import Union

def format_relative_time(timestamp: Union[str, float]) -> str:
    """
    Convert UTC timestamp to local timezone and return relative time string.
    
    Args:
        timestamp: Either ISO format timestamp string with UTC timezone (ending with 'Z')
                  or Unix timestamp in milliseconds
        
    Returns:
        Formatted relative time string (e.g. "5 minutes ago", "2 hours ago", "3 days ago")
    """
    if not timestamp:
        return "Unknown"
        
    # Convert to local timezone
    try:
        # First try parsing as ISO format
        try:
            dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        except ValueError:
            # If that fails, try parsing as Unix timestamp
            try:
                ts = float(timestamp)
                dt = datetime.fromtimestamp(ts/1000, tz=timezone.utc)
            except (ValueError, TypeError):
                return "Invalid timestamp"
            
        local_dt = dt.astimezone()  # Convert to local timezone
        
        # Calculate relative time
        now = datetime.now(timezone.utc).astimezone()  # Get current time in local timezone
        delta = now - local_dt
        
        if delta.days == 0:
            if delta.seconds < 3600:
                minutes = delta.seconds // 60
                return f"{minutes} minutes ago"
            else:
                hours = delta.seconds // 3600
                return f"{hours} hours ago"
        else:
            return f"{delta.days} days ago"
    except ValueError:
        return "Invalid timestamp"

def format_role(role: str) -> str:
    split_role = role.split(":")
    return f"{split_role[1]}"