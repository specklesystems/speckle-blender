"""Convert Blender Metaball (META) objects into Speckle meshes.

Speckle has no implicit-surface primitive and the parquet bundle's SGEO encoder
drops any geometry it cannot map, so a metaball has to reach the viewer as
triangles. Blender already polygonizes the isosurface for the viewport, so we
borrow that result the way the text and surface paths do — at *viewport*
resolution, deliberately: matching what the user sees costs nothing, whereas
``render_resolution`` would mean mutating the datablock and re-evaluating.

Only the family basis has a mesh to give. Which object that is, and which
members are properties-only children, is decided by ``metaball_unpacker`` —
this module just converts what it is handed.
"""

from typing import Any, Dict, List

from bpy.types import MetaBall, Object

from specklepy.objects.geometry.mesh import Mesh

from .mesh_to_speckle import mesh_to_speckle_meshes
from .utils import apply_cached_properties, extract_custom_properties, temporary_mesh


def metaball_to_speckle_meshes(
    geometry_source: Object,
    scale_factor: float = 1.0,
    units: str = "m",
    apply_modifiers: bool = True,
) -> List[Mesh]:
    """Tessellate a metaball family into Speckle meshes.

    ``geometry_source`` must be the family *basis* — the only object Blender
    polygonizes the merged field onto. Its ``matrix_world`` is also the right
    transform: siblings are baked into basis-local space during polygonization,
    so ``mesh_to_speckle_meshes`` recovers world coordinates from the basis
    alone. A non-uniformly scaled basis genuinely deforms the blob, and the
    viewport shows the same deformation, so baking its transform stays faithful.

    Returns an empty list when the family tessellates to no faces — every
    element below the threshold, or a basis whose siblings are all hidden and
    which contributes nothing itself.
    """
    assert geometry_source.type == "META", "Geometry source must be a metaball"
    assert geometry_source.data is not None, "Metaball data cannot be None"

    with temporary_mesh(geometry_source, apply_modifiers) as mesh:
        if mesh is None or not mesh.polygons:
            return []

        meshes = mesh_to_speckle_meshes(geometry_source, mesh, scale_factor, units)

    # the polygonized mesh is a throwaway datablock, so any custom properties
    # the user set live on the MetaBall — carry them onto the geometry the way
    # the text and surface paths carry their own data-block properties
    data_properties = extract_custom_properties(geometry_source.data)
    for speckle_mesh in meshes:
        apply_cached_properties(speckle_mesh, data_properties)

    return meshes


def metaball_properties(
    blender_object: Object,
    family_name: str,
    is_family_object: bool,
    member_count: int,
) -> Dict[str, Any]:
    """Metaball metadata to publish alongside (or instead of) the geometry.

    Nested under a single ``metaball`` key so it flattens to
    ``properties.metaball.*`` paths in the bundle's eav table, matching
    ``text_properties``. ``elementTypes`` is a ``{type: count}`` dict rather
    than a list because the eav flattener skips list values — a list would
    survive a classic send and silently vanish from the bundle.

    A properties-only child publishes its ``location`` here: with no geometry
    of its own, that is the only record of where in the blob it pulled.
    """
    metaball: MetaBall = blender_object.data

    element_types: Dict[str, int] = {}
    for element in metaball.elements:
        element_types[element.type] = element_types.get(element.type, 0) + 1

    location = blender_object.matrix_world.translation
    properties: Dict[str, Any] = {
        "familyName": family_name,
        "isFamilyObject": is_family_object,
        "memberCount": member_count,
        "elementCount": len(metaball.elements),
        "elementTypes": element_types,
        "location": {"x": location.x, "y": location.y, "z": location.z},
    }

    if is_family_object:
        # resolution and threshold are family-wide settings that Blender only
        # reads off the basis, so they would be misleading on a child
        properties["resolution"] = metaball.resolution
        properties["renderResolution"] = metaball.render_resolution
        properties["threshold"] = metaball.threshold

    return {"metaball": properties}
