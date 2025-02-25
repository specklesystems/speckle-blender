from datetime import datetime, timezone

def format_relative_time(timestamp) -> str:
    """
    Convert UTC timestamp to local timezone and return relative time string.
    
    Args:
        timestamp: Either ISO format timestamp string with UTC timezone (ending with 'Z')
                  or Unix timestamp in milliseconds
        
    Returns:
        str: A human-readable relative time string. Possible formats:
            - "X minutes ago" (when less than an hour)
            - "X hours ago" (when less than a day)
            - "X days ago" (when more than a day)
            - "Unknown" (when timestamp is None or empty)
            - "Invalid timestamp" (when parsing fails)

    Note:
        The function handles timezone conversion automatically, converting UTC
        timestamps to the local timezone before calculating the relative time.
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
    """
    This function takes a Speckle role string in the format "prefix:role" and
    returns just the role part.

    Args:
        role (str): The role string to format, expected in the format "prefix:role"

    Returns:
        str: The extracted role name (everything after the colon)
    """
    split_role = role.split(":")
    return f"{split_role[1]}"