"""Convert Blender Surface (SURFACE) objects into Speckle meshes.

Blender's SURFACE objects are NURBS patches — Nurbs Surface, Tube, Sphere and
Torus all share the ``SurfaceCurve`` datablock. Speckle does have a NURBS
``Surface`` primitive, but the parquet bundle's SGEO encoder has no mapping for
it (``sgeo.encode`` raises for any type outside its primitive table), so an
exact surface could not reach the server on the default publish path. Blender
already tessellates these patches for the viewport, so we borrow that result the
way the text and solid-curve paths do.

Unlike a Curve object, a Surface has no wire fallback worth publishing: its
``splines`` are the control rows of the patch rather than a path the user drew,
and emitting them would draw a handful of loose lines where the viewport shows a
solid. So this path always tessellates — there is deliberately no
``curve_may_have_volume``-style heuristic in front of it.
"""

from typing import List

from bpy.types import Object, SurfaceCurve

from specklepy.objects.geometry.mesh import Mesh

from .mesh_to_speckle import mesh_to_speckle_meshes
from .utils import apply_cached_properties, extract_custom_properties, temporary_mesh


def surface_to_speckle_meshes(
    blender_object: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> List[Mesh]:
    """Convert a Blender Surface object to a list of Speckle meshes, one per
    material slot.

    Returns an empty list when the patch tessellates to no faces — a surface
    with too few control points in one direction to span a face — which makes
    ``convert_to_speckle`` drop the object.
    """
    assert blender_object.type == "SURFACE", "Object must be a surface"
    assert blender_object.data is not None, "Surface data cannot be None"

    surface_data: SurfaceCurve = blender_object.data

    with temporary_mesh(blender_object, apply_modifiers) as mesh:
        if mesh is None or not mesh.polygons:
            return []

        meshes = mesh_to_speckle_meshes(blender_object, mesh, scale_factor, units)

    # the tessellated mesh is a throwaway datablock, so any custom properties
    # the user set live on the SurfaceCurve — carry them onto the geometry the
    # way the text and curve paths carry their own data-block properties
    data_properties = extract_custom_properties(surface_data)
    for speckle_mesh in meshes:
        apply_cached_properties(speckle_mesh, data_properties)

    return meshes
