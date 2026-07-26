"""Convert Blender Text (FONT) objects into Speckle meshes.

Speckle has no text geometry primitive, and the parquet bundle's SGEO encoder
drops any geometry it can't map (see ``bundle_exporter._emit_object``), so text
has to reach the viewer as triangles. Blender already does that tessellation for
the viewport — ``Object.to_mesh()`` on a FONT object returns the filled and
extruded glyph outlines — so we borrow that result and reuse the regular mesh
converter rather than walking font curves ourselves.

The string itself, the typeface and the layout settings are published as
object-level ``properties`` so they stay queryable in the viewer even though the
glyphs are baked into geometry.
"""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import bpy
from bpy.types import Mesh as BMesh
from bpy.types import Object, TextCurve

from specklepy.objects.geometry.mesh import Mesh

from .mesh_to_speckle import mesh_to_speckle_meshes
from .utils import apply_cached_properties, extract_custom_properties


@contextmanager
def temporary_mesh(
    blender_object: Object, apply_modifiers: bool
) -> Iterator[Optional[BMesh]]:
    """Yield the tessellated mesh of ``blender_object``, freeing it afterwards.

    ``to_mesh()`` hands back a mesh owned by the object it was called on, so the
    matching ``to_mesh_clear()`` has to target that same object — the evaluated
    copy when modifiers were applied, the original otherwise.
    """
    source = blender_object
    if apply_modifiers and blender_object.modifiers:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        source = blender_object.evaluated_get(depsgraph)

    mesh: Optional[BMesh] = None
    try:
        mesh = source.to_mesh()
    except RuntimeError:
        # object state that Blender refuses to tessellate
        mesh = None

    try:
        yield mesh
    finally:
        if mesh is not None:
            source.to_mesh_clear()


def text_to_speckle_meshes(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> List[Mesh]:
    """Convert a Blender Text object to a list of Speckle meshes, one per
    material slot.

    Returns an empty list when the text produces no faces — an empty body, or a
    ``fill_mode`` of ``NONE`` with no extrusion or bevel to give it volume.
    """
    assert blender_object.type == "FONT", "Object must be a text object"
    assert blender_object.data is not None, "Text data cannot be None"

    text_data: TextCurve = blender_object.data

    with temporary_mesh(blender_object, apply_modifiers) as mesh:
        if mesh is None or not mesh.polygons:
            return handle_unfilled_text(blender_object, text_data)

        meshes = mesh_to_speckle_meshes(blender_object, mesh, scale_factor, units)

    # the tessellated mesh is a throwaway datablock, so any custom properties
    # the user set live on the TextCurve — carry them onto the geometry the way
    # the mesh and curve paths carry their own data-block properties
    data_properties = extract_custom_properties(text_data)
    for speckle_mesh in meshes:
        apply_cached_properties(speckle_mesh, data_properties)

    return meshes


def handle_unfilled_text(blender_object: Object, text_data: TextCurve) -> List[Mesh]:
    """Decide what to publish for a Text object that tessellates to no faces.

    Reached when ``fill_mode`` is ``NONE`` and there is no extrude/bevel giving
    the glyphs volume, or when the body is empty. Returning an empty list makes
    ``convert_to_speckle`` drop the object entirely.

    TODO: pick the behaviour. Options:
      - drop it (current): matches how empty meshes/curves already behave, but
        the object disappears from the published model with no explanation.
      - force a fill: copy ``text_data``, set ``fill_mode = "BOTH"`` on the copy
        and tessellate that, so the viewer shows flat filled text. Costs a
        datablock copy per object and quietly overrides the user's setting.
      - publish geometry-less: return [] here but let the caller still emit a
        BlenderObject carrying the text properties, so the string survives as
        data even with nothing to draw.
    """
    return []


def text_properties(text_data: TextCurve) -> Dict[str, Any]:
    """Text metadata to publish alongside the geometry.

    Nested under a single ``text`` key so it flattens to ``properties.text.*``
    paths in the bundle's eav table (the flattener walks nested dicts but skips
    lists). Overwrites an object custom property of the same name — downstream
    consumers should be able to rely on ``properties.text`` meaning this.
    """
    body = text_data.body or ""
    font = text_data.font.name if text_data.font else None

    return {
        "text": {
            "body": body,
            "characterCount": len(body),
            "font": font,
            "size": text_data.size,
            "extrude": text_data.extrude,
            "bevelDepth": text_data.bevel_depth,
            "alignX": text_data.align_x,
            "alignY": text_data.align_y,
        }
    }
