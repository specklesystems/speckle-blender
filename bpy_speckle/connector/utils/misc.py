from datetime import datetime, timezone
import re


def format_relative_time(timestamp) -> str:
    """
    convert UTC timestamp to local timezone and return relative time string
    """
    if not timestamp:
        return "Unknown"

    # convert to local timezone
    try:
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            try:
                ts = float(timestamp)
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            except (ValueError, TypeError):
                return "Invalid timestamp"

        local_dt = dt.astimezone()

        # calculate relative time
        now = datetime.now(timezone.utc).astimezone()
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
    returns just the role part
    """
    split_role = role.split(":")
    return f"{split_role[1]}"


# C0 and C1 control characters, including newline/tab — UI labels are
# single-line and these are the only characters Blender's font stack
# (Noto fallback fonts + last-resort font) cannot draw
_NON_RENDERABLE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def strip_non_renderable(text: str) -> str:
    """
    Remove characters Blender's UI cannot render.

    Display-only: call this from connector UI draw code. Names stored in
    window-manager state, model cards, collections and objects stay raw.
    """
    return _NON_RENDERABLE.sub("", text)
