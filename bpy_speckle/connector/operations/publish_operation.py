"""Publish a converted scene as an artifact bundle.

Conversion itself lives in ``converter.to_speckle.scene_to_speckle``; this
module owns only what needs a network: the client, ``send()``, and metrics.
Callers pass the account/project/model ids explicitly — operations never read
``WindowManager`` state, so every caller (main panel or model card) uses the
same contract.
"""

import os
import shutil

import bpy
from bpy.types import Context
from typing import List, Optional, Tuple

from specklepy.bundle import BundleBuilder, SendOptions, send
from specklepy.objects.models.collections.collection import Collection
from specklepy.logging.exceptions import SpeckleException, WorkspacePermissionException

from ...converter.to_speckle.bundle_exporter import (
    BlenderBundleExporter,
    blender_producer,
)
from ...converter.to_speckle.scene_to_speckle import (
    build_collection_hierarchy,
    count_objects_in_collection,
)
from ..speckle_api import client_cache, get_project_workspace_id
from specklepy.logging import metrics
from ... import ADDON_INFO


def _send_bundle(
    client, project_id: str, model_id: str, root_collection: Collection
) -> str:
    """Write the artifact bundle locally and send it. Returns the version id.

    Conversion happens entirely before ``send()`` is called: nothing in the
    walk needs a version id (specklepy renames the files onto the reserved id
    itself), and a scene that converts to nothing raises here without ever
    creating an ingestion, so no orphan is left on the server. From that point
    on specklepy's ``send()`` owns the flow — ingestion creation, version-id
    reservation, upload, and ``fail_with_error`` teardown on any exception —
    the C# ``IBundleBuilder`` boundary.
    """
    builder = BundleBuilder(blender_producer(), root_collection.units)
    try:
        exporter = BlenderBundleExporter(builder)
        object_count = exporter.export(root_collection)

        for geo_id, error in exporter.conversion_errors:
            print(f"Skipped geometry '{geo_id}' in bundle: {error}")

        if object_count == 0:
            raise SpeckleException("No objects could be written to the artifact bundle")

        file_name = bpy.path.basename(bpy.data.filepath) or "Untitled.blend"
        file_size_bytes: Optional[int] = None
        if bpy.data.filepath:
            try:
                file_size_bytes = os.path.getsize(bpy.data.filepath)
            except OSError:
                pass

        try:
            result = send(
                client.account,
                project_id,
                model_id,
                builder,
                SendOptions(file_name=file_name, file_size_bytes=file_size_bytes),
            )
        except SpeckleException as e:
            # send() raises when the server does not reserve a version id for
            # the ingestion; surface that as the capability gap it is
            if "pre-allocate" in str(e):
                raise SpeckleException(
                    "This server does not support artifact bundles; publishing "
                    "from this connector needs a server with the /api/v2 data "
                    "endpoints."
                ) from e
            raise
        return result.version_id
    finally:
        # send() removes the bundle directory on success; this covers every
        # failure path (conversion, reservation, upload)
        shutil.rmtree(builder.directory, ignore_errors=True)


def publish_operation(
    context: Context,
    account_id: str,
    project_id: str,
    model_id: str,
    objects_to_convert: List,
    apply_modifiers: bool = True,
) -> Tuple[bool, str, Optional[str]]:
    """
    publish objects to speckle

    There is no version-message input: the ``complete`` call that creates the
    version has no message field (a server-side API gap), so the publish
    buttons act immediately with no dialog.
    """
    try:
        # get cached client
        client = client_cache.get_client(account_id)
        if not client:
            return False, "No Speckle client found", None

        # build collection hierarchy and convert objects
        root_collection = build_collection_hierarchy(
            context, objects_to_convert, apply_modifiers
        )

        if not root_collection:
            return False, "No objects could be converted to Speckle format", None

        version_id = _send_bundle(client, project_id, model_id, root_collection)

        # Get account for metrics tracking
        from specklepy.api.credentials import get_local_accounts

        account = next(
            (acc for acc in get_local_accounts() if acc.id == account_id),
            None,
        )

        if account:
            # track metrics
            metrics.set_host_app("blender")
            metrics.track(
                metrics.SEND,
                account,
                {
                    "ui": "dui3",
                    "hostAppVersion": ".".join(map(str, ADDON_INFO["blender"])),
                    "core_version": ".".join(map(str, ADDON_INFO["version"])),
                    "workspace_id": get_project_workspace_id(client, project_id),
                },
            )

        # count total objects for success message
        total_objects = count_objects_in_collection(root_collection)

        return (
            True,
            f"Successfully published {total_objects} objects with hierarchy to Speckle",
            version_id,
        )

    except WorkspacePermissionException as e:
        return False, f"Permission denied: {str(e)}", None

    except Exception as e:
        import traceback

        traceback.print_exc()
        # Clear cache on error to prevent stale clients
        client_cache.clear()
        return False, f"Failed to publish: {str(e)}", None
