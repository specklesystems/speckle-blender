"""The connector's one seam onto the Speckle server and local credentials.

Everything that talks GraphQL or reads ``Accounts.db`` credentials lives
behind this package; ``ui`` and ``blender_operators`` import from the package,
never from its modules, so the internal layout is free to change. Failure
policy is owned by ``client_cache`` (see its docstring) instead of being
copy-pasted at call sites.

This package requires specklepy, so nothing here may be imported before
``ensure_dependencies()`` has run (in practice: never at ``connector.ui``
package-init time).
"""

from .client_cache import client_cache, get_account_from_id  # noqa: F401
from .accounts import (  # noqa: F401
    get_account_enum_items,
    get_active_workspace,
    get_default_account_id,
    get_server_url_by_account_id,
    get_startup_account_id,
    get_workspaces,
)
from .permissions import (  # noqa: F401
    can_create_model,
    can_create_project_in_workspace,
    can_create_version,
    can_load,
)
from .projects import (  # noqa: F401
    create_project,
    get_project_workspace_id,
    get_projects_for_account,
)
from .models import create_model, get_models_for_project  # noqa: F401
from .versions import get_latest_version, get_versions_for_model  # noqa: F401
from .url_resolver import (  # noqa: F401
    ParsedSpeckleUrl,
    ResolvedSpeckleUrl,
    UnsupportedUrlError,
    is_same_server,
    parse_speckle_url,
    resolve_speckle_url,
)
