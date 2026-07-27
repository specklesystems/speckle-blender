"""Material identity fixture: two differently-named but visually identical materials.

This is the case behind commit d7e3c31 ("pass material names into the bundle").
Upstream ``add_material`` wrote ``name=None``, so two materials that differ only
by name interned to the same key and collapsed into one — objects silently
shared a material. Nothing looks wrong in the viewer, because the collapsed
material renders exactly like both originals.

The fixture builds the ambiguous scene. What counts as correct here is a
judgement call about material identity, so EXPECT is left for a human — see the
TODO below.
"""

import bmesh
import bpy


def _cube(name, material):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _grey(name):
    """A material identical to every other _grey() but for its name."""
    material = bpy.data.materials.new(name)
    material.diffuse_color = (0.5, 0.5, 0.5, 1.0)
    material.roughness = 0.5
    material.metallic = 0.0
    return material


def build():
    return [
        _cube("CubeA", _grey("Concrete")),
        _cube("CubeB", _grey("Plaster")),
        # a third object reusing CubeA's material — these two *should* share
        _cube("CubeC", bpy.data.materials["Concrete"]),
    ]


# TODO(bilal): pin the material identity contract for this scene.
#
# Available EXPECT keys: objects, geometries, geometry_types, collections,
# collection_parents, object_collections, materials (a count), material_names
# (an exact name set), relations (per-name counts, e.g. HAS_MATERIAL),
# eav_paths, properties.
#
# The design question: is a Speckle material identified by its appearance or by
# its Blender name? Pinning material_names == ["Concrete", "Plaster"] with
# HAS_MATERIAL == 3 says name is part of identity — distinct names stay
# distinct, and CubeC reuses Concrete rather than creating a duplicate. Pinning
# materials == 1 would say appearance alone decides, which is the pre-d7e3c31
# behaviour. Whichever you pin becomes the contract this fixture defends, so
# it's worth being deliberate rather than just recording what runs today.
#
# Run `tools/run_fixture.sh duplicate_materials` first — with no EXPECT it
# prints a report instead of asserting, so you can see the real numbers.
EXPECT = {}
