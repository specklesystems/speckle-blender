import re
import sys


def patch(tag):
    print(f"Patching version: {tag}")
    bpy_file = "bpy_speckle/__init__.py"
    tag = tag.split(".")

    with open(bpy_file, "r") as file:
        lines = file.readlines()

        for (index, line) in enumerate(lines):
            if '"version":' in line:
                lines[index] = f'    "version": ({tag[0]}, {tag[1]}, {tag[2]}),\n'
                print(f"Patched version number in {bpy_file}")
                break

        with open(bpy_file, "w") as file:
            file.writelines(lines)


def get_specklepy_version():
    version = "2.3.3"
    with open("pyproject.toml", "r") as f:
        lines = [line for line in f if line.startswith("specklepy = ")]
        if not lines:
            raise Exception("Could not find specklepy in pyproject.toml")
        match = re.search(r"[0-9]+(\.[0-9]+)*", lines[0])
        if match:
            version = match[0]
    print(version)


def main():
    if len(sys.argv) < 2:
        return

    # get specklepy version to install
    if sys.argv[1] == "specklepy":
        get_specklepy_version()

    # patch blender connector version
    else:
        tag = sys.argv[1]
        if not re.match(r"[0-9]+(\.[0-9]+)*$", tag):
            raise ValueError(f"Invalid tag provided: {tag}")

        patch(tag)


if __name__ == "__main__":
    main()
