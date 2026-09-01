"""Load a version by downloading its artifact bundle and baking it directly.

The bundle is the only receive path. A published version's ``referencedObject``
is a bundle reference (``bundle.<project>.<model>.<version>``), not an object
id, and versions published before the bundle era are rewritten into bundles by
the server-side migration service — so a version without a bundle is an error
to surface, never something to fall back from.

specklepy owns the transport (`specklepy.bundle.download`) and the parse
(`specklepy.bundle.bundle_reader` wrapped in a ``Model``); the connector owns
only the bake into ``bpy.data``.
"""

import tempfile
from typing import Dict, Union

import bpy
from bpy.types import Context
from specklepy.api import host_applications
from specklepy.api.inputs.version_inputs import MarkReceivedVersionInput
from specklepy.bundle.bundle_reader import read_bundle
from specklepy.bundle.download import download_bundle
from specklepy.bundle.model import Model
from specklepy.logging import metrics
from specklepy.logging.exceptions import SpeckleException

from ... import ADDON_INFO
from ...converter.from_bundle.bundle_to_native import bake_bundle
from ..utils.account_manager import _client_cache
from ..utils.project_manager import get_project_workspace_id


def _mark_received(client, version, project_id: str) -> None:
    """Tell the server the version was received, and track the metric."""
    metrics.set_host_app("blender")
    client.version.received(
        MarkReceivedVersionInput(
            version_id=version.id,
            project_id=project_id,
            source_application="blender",
        )
    )

    metrics.track(
        metrics.RECEIVE,
        client.account,
        {
            "ui": "dui3",
            "hostAppVersion": ".".join(map(str, ADDON_INFO["blender"])),
            "core_version": ".".join(map(str, ADDON_INFO["version"])),
            "sourceHostApp": host_applications.get_host_app_from_string(
                version.source_application
            ).slug,
            "isMultiplayer": version.author_user.id != client.account.userInfo.id,
            "workspace_id": get_project_workspace_id(client, project_id),
        },
    )


def load_operation(
    context: Context,
    account_id: str,
    project_id: str,
    model_id: str,
    version_id: str,
    model_name: str,
    instance_loading_mode: str = "INSTANCE_PROXIES",
) -> Dict[str, Union[bpy.types.Collection, bpy.types.Object]]:
    """Download the version's artifact bundle and bake it.

    Every input is an explicit parameter — this function never reads
    ``WindowManager`` state, so the model-card flow and the main-panel flow
    call it identically.
    """
    # Raise rather than return {}: an empty result is a legitimate success for a
    # version with no objects, so it cannot double as the failure signal.
    client = _client_cache.get_client(account_id)
    if not client:
        raise ValueError(f"No Speckle client found for account {account_id}")

    version = client.version.get(version_id, project_id)

    # The bundle stays on disk only for the duration of the bake; geometry is
    # parsed lazily from the directory, so the bake must run inside this block.
    with tempfile.TemporaryDirectory(prefix="speckle-receive-") as bundle_dir:
        files = download_bundle(
            client.account, project_id, model_id, version.id, bundle_dir
        )
        if not files:
            raise SpeckleException(
                f"Version {version.id} has no artifact bundle yet; it may not "
                "have been migrated. Re-publish the model, or wait for the "
                "server's migration of older versions to finish."
            )

        model = Model(
            project_id,
            model_id,
            version.id,
            bundle_dir,
            files,
            read_bundle(bundle_dir),
        )
        result = bake_bundle(
            model,
            f"{model_name} - {version.id}",
            instance_loading_mode=instance_loading_mode,
        )

    if result.skipped_by_type:
        summary = ", ".join(
            f"{count} {type_name}"
            for type_name, count in result.skipped_by_type.items()
        )
        print(
            f"[Speckle] Geometry not yet supported on the bundle load path: {summary}"
        )
    for app_id, error in result.decode_errors:
        print(f"[Speckle] Could not decode geometry for '{app_id}': {error}")
    if result.unmapped_containers:
        summary = ", ".join(
            f"{count} {subtype}"
            for subtype, count in result.unmapped_containers.items()
        )
        print(f"[Speckle] Grouping not yet mapped on the bundle load path: {summary}")
    if result.dropped_properties:
        print(
            f"[Speckle] {result.dropped_properties} custom properties could not be"
            " stored (conflicting paths or unsupported values) and were dropped"
        )

    print(f"\nLoad process completed. Imported {len(result.objects)} objects.")
    for area in context.screen.areas:
        if area.type == "OUTLINER":
            area.tag_redraw()

    _mark_received(client, version, project_id)
    return result.objects
