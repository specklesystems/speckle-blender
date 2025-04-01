import re
import sys

def patch_addon(simple_version: str):
    """Patches the __init__.py bl_info version within the connector init file"""
    FILE_PATH = "bpy_speckle/__init__.py"
    version = simple_version.split(".")

    with open(FILE_PATH, "r") as file:
        lines = file.readlines()

        for (index, line) in enumerate(lines):
            if '"version":' in line:
                lines[index] = f'    "version": ({version[0]}, {version[1]}, {version[2]}),\n'

        with open(FILE_PATH, "w") as file:
            file.writelines(lines)

def patch_manifest(simple_version: str):
    """Patches the connector version within the connector init file"""
    FILE_PATH = "bpy_speckle/blender_manifest.toml"
    version = simple_version.split(".")

    with open(FILE_PATH, "r") as file:
        lines = file.readlines()

        for (index, line) in enumerate(lines):
            if line.startswith('version ='):
                lines[index] = f'version = "{version[0]}.{version[1]}.{version[2]}",\n'
                print(f"Patched connector version number in {FILE_PATH}")
                break

        with open(FILE_PATH, "w") as file:
            file.writelines(lines)

def main():
    tag = sys.argv[1]
    if not re.match(r"([0-9]+)\.([0-9]+)\.([0-9]+)", tag):
        raise ValueError(f"Invalid tag provided: {tag}")

    print(f"Patching version: {tag}")
    simple_version = tag.split("-")[0]
    patch_addon(simple_version)
    patch_manifest(simple_version)


if __name__ == "__main__":
    main()
