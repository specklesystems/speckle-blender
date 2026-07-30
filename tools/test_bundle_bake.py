"""Bakes synthetic cross-connector bundles in headless Blender and checks the
Blender-visible shape and diagnostics that come out.

The publish fixtures can only make Blender-shaped bundles, so the container
axes Blender never writes — models, systems, groups — are fabricated with the
same table writer as ``test_bundle_reader.py`` and pushed through the real
receive path (``read_bundle`` -> ``bake_bundle``):

    /Applications/Blender.app/Contents/MacOS/Blender --background \\
        --factory-startup -noaudio --python tools/test_bundle_bake.py

Most relationship scenarios carry no geometry on purpose: a geometry-less
object bakes to a real (shapeless) Blender object, which is all placement
assertions need. Geometry characterization scenarios use real SGEO payloads.
"""

import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the repo root must precede the symlinked extension so `import bpy_speckle`
# resolves to the working tree, not the installed add-on
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import bpy  # noqa: E402

from test_bundle_reader import (  # noqa: E402
    DISPLAY,
    DISPLAY_INSTANCE,
    HAS_MATERIAL,
    IN_COLLECTION,
    IN_GROUP,
    IN_MODEL,
    IN_SYSTEM,
    SUBELEMENT,
    write_bundle,
)


def bake(**bundle_kwargs):
    """Write a synthetic bundle, then run the real receive path on it."""
    from bpy_speckle.converter.from_bundle.bundle_reader import read_bundle
    from bpy_speckle.converter.from_bundle.bundle_to_native import bake_bundle

    bpy.ops.wm.read_factory_settings(use_empty=True)
    with tempfile.TemporaryDirectory() as bundle_dir:
        write_bundle(bundle_dir, **bundle_kwargs)
        bundle = read_bundle(bundle_dir)
    return bake_bundle(bundle, "Received")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def children(collection) -> set:
    return {c.name for c in collection.children}


def homes(result, application_id: str) -> set:
    return {c.name for c in result.objects[application_id].users_collection}


def translation(x: float, y: float, z: float) -> str:
    return f"1,0,0,{x},0,1,0,{y},0,0,1,{z},0,0,0,1"


def navis_federation() -> None:
    """Two models become the outermost tier; the network parks under Systems.

    The duct appears both in its model and in its network — membership is
    additive, not a move.
    """
    result = bake(
        containers=[
            (1, "Supply Air", None, "Network"),
            (2, "hvac.nwc", None, "Model"),
            (3, "arch.nwc", None, "Model"),
        ],
        objects=["duct-1", "wall-1"],
        relations=[(IN_SYSTEM, 0, 1), (IN_MODEL, 0, 2), (IN_MODEL, 1, 3)],
    )
    check(
        children(result.root_collection) == {"hvac.nwc", "arch.nwc", "Systems"},
        f"model tier + Systems branch expected, got {children(result.root_collection)}",
    )
    check(homes(result, "duct-1") == {"hvac.nwc", "Supply Air"}, "duct multi-links")
    check(homes(result, "wall-1") == {"arch.nwc"}, "wall sits in its model")
    check(not result.unmapped_containers, "every axis here has a mapping")


def single_model_maps_onto_root() -> None:
    """One model adds no folder level, exactly like a lone authored root."""
    result = bake(
        containers=[(1, "site.nwc", None, "Model")],
        objects=["fence-1"],
        relations=[(IN_MODEL, 0, 1)],
    )
    check(
        children(result.root_collection) == set(),
        "a single model must not nest a redundant folder",
    )
    check(homes(result, "fence-1") == {"Received"}, "object sits at the root")


def rhino_groups_beside_layers() -> None:
    """The object keeps its layer AND its groups; groups nest under one branch."""
    result = bake(
        containers=[
            (2, "GroupA", None, "Group"),
            (3, "GroupB", 2, "Group"),
            (5, "Root", None, "Collection"),
            (6, "Layer1", 5, "Collection"),
        ],
        objects=["curve-1"],
        relations=[(IN_COLLECTION, 0, 6), (IN_GROUP, 0, 2), (IN_GROUP, 0, 3)],
    )
    root = result.root_collection
    check(
        children(root) == {"Layer1", "Groups"},
        f"authored tree + Groups branch expected, got {children(root)}",
    )
    groups = root.children["Groups"]
    check(children(groups) == {"GroupA"}, "top group under the branch")
    check(children(groups.children["GroupA"]) == {"GroupB"}, "groups nest")
    check(
        homes(result, "curve-1") == {"Layer1", "GroupA", "GroupB"},
        "layer plus both groups",
    )


def unknown_subtype_is_surfaced_not_baked() -> None:
    """A subtype we cannot map must be reported, never an empty folder."""
    result = bake(
        containers=[(1, "Mystery", None, "Zone")],
        objects=[],
        relations=[],
    )
    check(
        children(result.root_collection) == set(),
        "no misleading empty collection",
    )
    check(
        result.unmapped_containers == {"Zone": 1},
        f"tally expected, got {result.unmapped_containers}",
    )


def revit_parameter_paths_bake_as_groups() -> None:
    """A Revit parameter path is one flat eav key well past Blender's 63-byte
    IDProperty name limit; written verbatim it aborted the whole bake. The
    paths must come back as nested property groups, an over-long single
    segment is fitted rather than raised, and a scalar/subtree collision is
    tallied — never an exception.
    """
    keynote = (
        "properties.Parameters.Instance Parameters.Identity Data"
        ".Keynote Text With A Very Long Parameter Name"
    )
    length = "properties.Parameters.Instance Parameters.Dimensions.Length"
    result = bake(
        containers=[(1, "Root", None, "Collection")],
        objects=["wall-1"],
        relations=[(IN_COLLECTION, 0, 1)],
        properties=[
            (0, keynote, "K1"),
            (0, length, 3.5),
            (0, "properties." + "x" * 80, True),
            (0, "properties.A", 1.0),
            (0, "properties.A.B", 2.0),
        ],
    )
    wall = result.objects["wall-1"]
    params = wall["Parameters"]["Instance Parameters"]
    check(
        params["Identity Data"]["Keynote Text With A Very Long Parameter Name"] == "K1",
        "deep parameter path must bake as nested groups",
    )
    check(params["Dimensions"]["Length"] == 3.5, "sibling subtree survives")
    check(bool(wall["x" * 63]), "an over-long segment is fitted, value kept")
    check(wall["A"] == 1.0, "first arrival wins a scalar/subtree collision")
    check(
        result.dropped_properties == 1,
        f"the colliding path is tallied, got {result.dropped_properties}",
    )


def revit_subelement_parenting_preserves_world_transform() -> None:
    """Hierarchy metadata must not reinterpret absolute Revit placements.

    Revit family subelements are independent INSTANCE nodes whose transforms
    are already world-space. Reconstructing the SUBELEMENT hierarchy in Blender
    must preserve that world transform rather than applying the parent's
    placement a second time.
    """
    result = bake(
        containers=[],
        objects=["window", "frame", "metadata"],
        definitions=[(1, "window-definition"), (3, "frame-definition")],
        instances=[
            (2, 1, translation(20, 30, 0), "m"),
            (4, 3, translation(20, 31, 2), "m"),
        ],
        relations=[
            (DISPLAY_INSTANCE, 0, 2),
            (DISPLAY_INSTANCE, 1, 4),
            (SUBELEMENT, 0, 1),
            (SUBELEMENT, 0, 2),
        ],
    )
    bpy.context.view_layer.update()

    window = result.objects["window"]
    frame = result.objects["frame"]
    metadata = result.objects["metadata"]
    check(frame.parent is window, "SUBELEMENT hierarchy must be reconstructed")
    check(
        tuple(round(v, 6) for v in frame.matrix_world.translation) == (20.0, 31.0, 2.0),
        f"frame world transform must survive parenting, got {frame.matrix_world.translation}",
    )
    check(metadata.parent is window, "properties-only subelement must be parented")
    check(
        tuple(round(v, 6) for v in metadata.matrix_world.translation)
        == (20.0, 30.0, 0.0),
        "properties-only subelement must remain identity-local to its owner",
    )


def parenting_endpoints_get_meaningful_origins() -> None:
    """Parenting participants recentre onto their geometry; bystanders do not.

    Blender draws relationship lines origin-to-origin, and direct-baked meshes
    all have their origin at (0, 0, 0) — so before recentring, every SUBELEMENT
    link drew a line from the element back to the world origin. Both endpoints
    of a link must move onto their geometry (world position unchanged), a
    properties-only parent moves to the median of its placed children, and an
    object outside any parent link keeps the identity transform the dialect
    promises.
    """
    from specklepy.bundle import sgeo
    from specklepy.objects.geometry import Mesh

    def quad(cx: float, cy: float, cz: float) -> bytes:
        """A unit quad centred on (cx, cy, cz), world-baked like a real publish."""
        return sgeo.encode(
            Mesh(
                vertices=[
                    cx - 0.5,
                    cy - 0.5,
                    cz,
                    cx + 0.5,
                    cy - 0.5,
                    cz,
                    cx + 0.5,
                    cy + 0.5,
                    cz,
                    cx - 0.5,
                    cy + 0.5,
                    cz,
                ],
                faces=[4, 0, 1, 2, 3],
                units="m",
            )
        )

    # "base" sits above the median-placed "assembly" and is deliberately last
    # in bundle order: linking assembly under base must preserve assembly's
    # world (anchoring), not drag it — and wall/panel under it — onto base.
    result = bake(
        containers=[],
        objects=["wall", "panel", "assembly", "lone", "base"],
        geometries=[
            (0, "mesh", quad(10, 20, 0)),
            (1, "mesh", quad(12, 20, 4)),
            (2, "mesh", quad(30, 5, 1)),
            (3, "mesh", quad(8, 24, 0)),
        ],
        relations=[
            (DISPLAY, 0, 0),
            (DISPLAY, 1, 1),
            (DISPLAY, 3, 2),
            (DISPLAY, 4, 3),
            (SUBELEMENT, 2, 0),  # assembly (properties-only) -> wall
            (SUBELEMENT, 0, 1),  # wall -> panel
            (SUBELEMENT, 4, 2),  # base -> assembly, linked after the median
        ],
    )
    bpy.context.view_layer.update()

    def world_translation(obj) -> tuple:
        return tuple(round(v, 6) for v in obj.matrix_world.translation)

    def world_vertex(obj, index: int) -> tuple:
        return tuple(
            round(v, 6) for v in obj.matrix_world @ obj.data.vertices[index].co
        )

    wall = result.objects["wall"]
    panel = result.objects["panel"]
    assembly = result.objects["assembly"]
    lone = result.objects["lone"]

    check(
        world_translation(wall) == (10.0, 20.0, 0.0),
        f"a subelement parent recentres onto its geometry, got {world_translation(wall)}",
    )
    check(
        world_vertex(wall, 0) == (9.5, 19.5, 0.0),
        f"recentring must not move the geometry, got {world_vertex(wall, 0)}",
    )
    check(panel.parent is wall, "SUBELEMENT hierarchy must be reconstructed")
    check(
        world_translation(panel) == (12.0, 20.0, 4.0),
        f"a subelement child recentres onto its geometry, got {world_translation(panel)}",
    )
    check(
        world_vertex(panel, 0) == (11.5, 19.5, 4.0),
        f"child geometry must stay put under parenting, got {world_vertex(panel, 0)}",
    )
    check(wall.parent is assembly, "chained SUBELEMENT parenting holds")
    check(
        world_translation(assembly) == (10.0, 20.0, 0.0),
        "a properties-only parent moves to the median of its placed children, "
        f"got {world_translation(assembly)}",
    )
    base = result.objects["base"]
    check(assembly.parent is base, "the anchored parent still links upward")
    check(
        world_translation(assembly) == (10.0, 20.0, 0.0)
        and world_vertex(wall, 0) == (9.5, 19.5, 0.0),
        "linking a median-placed parent under a later grandparent must not "
        f"drag it or its children, got {world_translation(assembly)} / "
        f"{world_vertex(wall, 0)}",
    )
    check(
        world_translation(lone) == (0.0, 0.0, 0.0)
        and world_vertex(lone, 0) == (29.5, 4.5, 1.0),
        "an object outside any parent link keeps the identity transform",
    )


def _primitive_payloads() -> list[tuple[str, bytes]]:
    """One valid SGEO payload for every primitive family the bake supports."""
    from specklepy.bundle import sgeo
    from specklepy.objects.geometry import (
        Arc,
        Box,
        Circle,
        Curve,
        Ellipse,
        Line,
        Mesh,
        Plane,
        Point,
        PointCloud,
        Polycurve,
        Polyline,
        Spiral,
        Vector,
    )
    from specklepy.objects.primitive import Interval

    def point(x: float, y: float, z: float, units: str = "m") -> Point:
        return Point(x=x, y=y, z=z, units=units)

    def vector(x: float, y: float, z: float) -> Vector:
        return Vector(x=x, y=y, z=z, units="m")

    plane = Plane(
        origin=point(0, 0, 0),
        normal=vector(0, 0, 1),
        xdir=vector(1, 0, 0),
        ydir=vector(0, 1, 0),
        units="m",
    )
    line = Line(
        start=point(0, 0, 0, "mm"),
        end=point(1000, 0, 0, "mm"),
        units="mm",
    )
    polyline = Polyline(value=[0, 0, 0, 1, 1, 0, 2, 0, 0], units="m")
    curve = Curve(
        degree=2,
        periodic=False,
        rational=False,
        points=[0, 0, 0, 1, 1, 0, 2, 0, 0],
        weights=[1, 1, 1],
        knots=[0, 0, 0, 1, 1, 1],
        closed=False,
        displayValue=polyline,
        units="m",
    )
    spiral = Spiral(
        start_point=point(0, 0, 0),
        end_point=point(2, 0, 1),
        plane=plane,
        turns=1,
        pitch=1,
        pitch_axis=vector(0, 0, 1),
        units="m",
    )
    spiral["displayValue"] = polyline

    primitives = [
        (
            "mesh",
            Mesh(
                vertices=[0, 0, 0, 1000, 0, 0, 0, 1000, 0],
                faces=[3, 0, 1, 2],
                units="mm",
            ),
        ),
        (
            "box",
            Box(
                basePlane=plane,
                xSize=Interval(start=0, end=1),
                ySize=Interval(start=0, end=1),
                zSize=Interval(start=0, end=1),
                units="m",
            ),
        ),
        ("line", line),
        ("polyline", polyline),
        ("polycurve", Polycurve(segments=[line, polyline], units="m")),
        ("curve", curve),
        (
            "arc",
            Arc(
                plane=plane,
                startPoint=point(1, 0, 0),
                midPoint=point(0, 1, 0),
                endPoint=point(-1, 0, 0),
                units="m",
            ),
        ),
        (
            "circle",
            Circle(plane=plane, center=point(0, 0, 0), radius=1, units="m"),
        ),
        (
            "ellipse",
            Ellipse(plane=plane, first_radius=2, second_radius=1, units="m"),
        ),
        ("spiral", spiral),
        (
            "points",
            PointCloud(
                points=[point(0, 0, 0), point(1, 2, 3)],
                units="m",
            ),
        ),
        ("points", point(2000, 3000, 4000, "mm")),
    ]
    return [(kind, sgeo.encode(primitive)) for kind, primitive in primitives]


def all_sgeo_primitive_families_bake() -> None:
    """Every supported SGEO family produces its documented Blender shape."""
    payloads = _primitive_payloads()
    application_ids = [
        "mesh",
        "box",
        "line",
        "polyline",
        "polycurve",
        "curve",
        "arc",
        "circle",
        "ellipse",
        "spiral",
        "point-cloud",
        "single-point",
    ]
    result = bake(
        containers=[],
        objects=application_ids,
        geometries=[
            (index, kind, content) for index, (kind, content) in enumerate(payloads)
        ],
        relations=[(DISPLAY, index, index) for index in range(len(application_ids))],
    )

    for application_id in ("mesh", "box"):
        obj = result.objects[application_id]
        check(isinstance(obj.data, bpy.types.Mesh), f"{application_id} -> Mesh")
        check(bool(obj.data.polygons), f"{application_id} must have faces")
    check(
        round(max(v.co.x for v in result.objects["mesh"].data.vertices), 6) == 1.0,
        "mesh millimetres must scale into scene metres",
    )

    curve_ids = application_ids[2:10]
    for application_id in curve_ids:
        obj = result.objects[application_id]
        check(isinstance(obj.data, bpy.types.Curve), f"{application_id} -> Curve")
        check(bool(obj.data.splines), f"{application_id} must have a spline")
    line = result.objects["line"]
    check(
        round(line.data.splines[0].points[-1].co.x, 6) == 1.0,
        "curve millimetres must scale into scene metres",
    )

    point_cloud = result.objects["point-cloud"]
    check(isinstance(point_cloud.data, bpy.types.Mesh), "point cloud -> Mesh")
    check(
        len(point_cloud.data.vertices) == 2 and not point_cloud.data.polygons,
        "point cloud must become a vertex-only mesh",
    )
    single = result.objects["single-point"]
    check(single.data is None, "one decoded point must become an Empty")
    check(
        tuple(round(v, 6) for v in single.location) == (2.0, 3.0, 4.0),
        f"point units must scale, got {single.location}",
    )


def mixed_geometry_families_stay_one_scene_element() -> None:
    """Mesh wins as primary; curve/points remain fixed children everywhere."""
    from specklepy.bundle import sgeo
    from specklepy.objects.geometry import Line, Mesh, Point, PointCloud

    mesh = Mesh(
        vertices=[10, 0, 0, 12, 0, 0, 10, 2, 0],
        faces=[3, 0, 1, 2],
        units="m",
    )
    line = Line(
        start=Point(x=20, y=0, z=0, units="m"),
        end=Point(x=22, y=0, z=0, units="m"),
        units="m",
    )
    points = PointCloud(
        points=[
            Point(x=30, y=0, z=0, units="m"),
            Point(x=31, y=0, z=0, units="m"),
        ],
        units="m",
    )
    result = bake(
        containers=[
            (1, "Root", None, "Collection"),
            (2, "Layer", 1, "Collection"),
            (3, "GroupA", None, "Group"),
        ],
        objects=["mixed"],
        geometries=[
            (0, "mesh", sgeo.encode(mesh)),
            (1, "line", sgeo.encode(line)),
            (2, "points", sgeo.encode(points)),
        ],
        relations=[
            (DISPLAY, 0, 0),
            (DISPLAY, 0, 1),
            (DISPLAY, 0, 2),
            (IN_COLLECTION, 0, 2),
            (IN_GROUP, 0, 3),
        ],
    )
    bpy.context.view_layer.update()

    primary = result.objects["mixed"]
    check(isinstance(primary.data, bpy.types.Mesh), "mesh must be primary")
    check(len(primary.children) == 2, "curve and points must be secondary parts")
    parts = [primary, *primary.children]
    for part in parts:
        check(
            {collection.name for collection in part.users_collection}
            == {"Layer", "GroupA"},
            f"every mixed-family part must share memberships, got {part.users_collection}",
        )

    curve = next(
        part for part in primary.children if isinstance(part.data, bpy.types.Curve)
    )
    points_part = next(
        part
        for part in primary.children
        if isinstance(part.data, bpy.types.Mesh) and not part.data.polygons
    )
    check(
        tuple(round(v, 6) for v in primary.matrix_world @ primary.data.vertices[0].co)
        == (10.0, 0.0, 0.0),
        "primary world geometry must survive recentering",
    )
    curve_point = curve.data.splines[0].points[0].co
    check(
        tuple(round(v, 6) for v in curve.matrix_world @ curve_point)[:3]
        == (20.0, 0.0, 0.0),
        "curve world geometry must survive parenting",
    )
    check(
        tuple(
            round(v, 6)
            for v in points_part.matrix_world @ points_part.data.vertices[0].co
        )
        == (30.0, 0.0, 0.0),
        "point-cloud world geometry must survive parenting",
    )


def material_binding_follows_source_geometry() -> None:
    """Two merged source meshes retain their own material face ranges."""
    from specklepy.bundle import sgeo
    from specklepy.objects.geometry import Mesh

    first = Mesh(
        vertices=[0, 0, 0, 1, 0, 0, 0, 1, 0],
        faces=[3, 0, 1, 2],
        units="m",
    )
    second = Mesh(
        vertices=[2, 0, 0, 3, 0, 0, 2, 1, 0],
        faces=[3, 0, 1, 2],
        units="m",
    )
    result = bake(
        containers=[],
        objects=["two-materials"],
        geometries=[
            (0, "mesh", sgeo.encode(first)),
            (1, "mesh", sgeo.encode(second)),
        ],
        materials=[
            (10, "Red", -65536, 1.0, 0.0, 0.5),
            (11, "Blue", -16776961, 1.0, 0.0, 0.5),
        ],
        relations=[
            (DISPLAY, 0, 0),
            (DISPLAY, 0, 1),
            (HAS_MATERIAL, 0, 10),
            (HAS_MATERIAL, 1, 11),
        ],
    )

    mesh = result.objects["two-materials"].data
    check(
        [material.name for material in mesh.materials] == ["Red", "Blue"],
        f"both geometry materials need slots, got {list(mesh.materials)}",
    )
    check(
        [mesh.materials[face.material_index].name for face in mesh.polygons]
        == ["Red", "Blue"],
        "each source mesh's faces must use its HAS_MATERIAL target",
    )


def unsupported_and_corrupt_geometry_isolated() -> None:
    """Unsupported and malformed blobs are diagnosed without aborting peers."""
    from specklepy.bundle import sgeo
    from specklepy.objects.geometry import Mesh

    triangle = Mesh(
        vertices=[0, 0, 0, 1, 0, 0, 0, 1, 0],
        faces=[3, 0, 1, 2],
        units="m",
    )
    malformed_faces = Mesh(
        vertices=[0, 0, 0, 1, 0, 0, 0, 1, 0],
        faces=[3, 0, 1, 2, 4, 0, 1],
        units="m",
    )
    result = bake(
        containers=[],
        objects=[
            "mixed-supported",
            "unsupported-only",
            "corrupt-sgeo",
            "corrupt-faces",
            "healthy-after-error",
        ],
        geometries=[
            (0, "mesh", sgeo.encode(triangle)),
            (1, "brep", b"unsupported"),
            (2, "surface", b"unsupported"),
            (3, "mesh", b"\x00"),
            (4, "mesh", sgeo.encode(malformed_faces)),
            (5, "mesh", sgeo.encode(triangle)),
        ],
        relations=[
            (DISPLAY, 0, 0),
            (DISPLAY, 0, 1),
            (DISPLAY, 1, 2),
            (DISPLAY, 2, 3),
            (DISPLAY, 3, 4),
            (DISPLAY, 4, 5),
        ],
    )

    check("mixed-supported" in result.objects, "supported portion must still bake")
    check("unsupported-only" not in result.objects, "unsupported-only object omitted")
    check("corrupt-sgeo" not in result.objects, "fully failed object omitted")
    check(
        "healthy-after-error" in result.objects, "one decode error must not abort bake"
    )
    check(
        result.skipped_by_type == {"brep": 1, "surface": 1},
        f"unknown types must be tallied, got {result.skipped_by_type}",
    )
    check(result.skipped_count == 2, "skipped_count remains unsupported blob count")
    check(
        len(result.decode_errors) == 1 and result.decode_errors[0][0] == "corrupt-sgeo",
        f"corrupt SGEO must be diagnosed, got {result.decode_errors}",
    )
    check(
        len(result.objects["corrupt-faces"].data.polygons) == 1,
        "malformed face count stops that mesh's remaining face stream",
    )


SCENARIOS = [
    navis_federation,
    single_model_maps_onto_root,
    rhino_groups_beside_layers,
    unknown_subtype_is_surfaced_not_baked,
    revit_parameter_paths_bake_as_groups,
    revit_subelement_parenting_preserves_world_transform,
    parenting_endpoints_get_meaningful_origins,
    all_sgeo_primitive_families_bake,
    mixed_geometry_families_stay_one_scene_element,
    material_binding_follows_source_geometry,
    unsupported_and_corrupt_geometry_isolated,
]


def main() -> int:
    failed = 0
    for scenario in SCENARIOS:
        try:
            scenario()
        except AssertionError as e:
            print(f"FAIL  {scenario.__name__}: {e}")
            failed += 1
        else:
            print(f"ok    {scenario.__name__}")
    if failed:
        print(f"\n{failed} of {len(SCENARIOS)} scenarios failed")
        return 1
    print(f"\nAll {len(SCENARIOS)} scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
