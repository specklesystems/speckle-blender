import re
import sys


def patch_connector(tag):
    """Patches the connector version within the connector init file"""
    bpy_file = "bpy_speckle/__init__.py"
    tag = tag.split(".")

    with open(bpy_file, "r") as file:
        lines = file.readlines()

        for index, line in enumerate(lines):
            if '"version":' in line:
                lines[index] = f'    "version": ({tag[0]}, {tag[1]}, {tag[2]}),\n'
                print(f"Patched connector version number in {bpy_file}")
                break

        with open(bpy_file, "w") as file:
            file.writelines(lines)


def main():
    tag = sys.argv[1]
    if not re.match(r"([0-9]+)\.([0-9]+)\.([0-9]+)", tag):
        raise ValueError(f"Invalid tag provided: {tag}")

    print(f"Patching version: {tag}")
    patch_connector(tag.split("-")[0])


if __name__ == "__main__":
    main()
