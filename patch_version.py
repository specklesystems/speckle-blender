import re
import sys


def patch_connector(tag):
    """Patches the connector version within the connector init file"""
    bpy_file = "bpy_speckle/__init__.py"
    tag = tag.split("-")[0]
    tag = tag.split(".")

    with open(bpy_file, "r") as file:
        lines = file.readlines()

        for (index, line) in enumerate(lines):
            if '"version":' in line:
                lines[index] = f'    "version": ({tag[0]}, {tag[1]}, {tag[2]}),\n'
                print(f"Patched connector version number in {bpy_file}")
                break

        with open(bpy_file, "w") as file:
            file.writelines(lines)


def patch_installer(tag):
    """Patches the installer with the correct connector version and specklepy version"""
    iss_file = "speckle-sharp-ci-tools/blender.iss"

    py_tag = get_specklepy_version()
    with open(iss_file, "r") as file:
        lines = file.readlines()
        lines.insert(11, f'#define SpecklepyVersion "{py_tag}"\n')
        lines.insert(11, f'#define AppVersion "{tag}"\n')

        with open(iss_file, "w") as file:
            file.writelines(lines)
            print(f"Patched installer with connector v{tag} and specklepy v{py_tag}")


def get_specklepy_version():
    """Get version of specklepy to install from the pyproject.toml"""
    version = "2.3.3"
    with open("pyproject.toml", "r") as f:
        lines = [line for line in f if line.startswith("specklepy = ")]
        if not lines:
            raise Exception("Could not find specklepy in pyproject.toml")
        match = re.search(r"[0-9]+(\.[0-9]+)*", lines[0])
        if match:
            version = match[0]
    return version


def main():
    if len(sys.argv) < 2:
        print(get_specklepy_version())
        return

    tag = sys.argv[1]
    if not re.match(r"([0-9]+)\.([0-9]+)\.([0-9]+)(?:-\w+)?$", tag):
        raise ValueError(f"Invalid tag provided: {tag}")

    print(f"Patching version: {tag}")
    patch_connector(tag)
    patch_installer(tag)


if __name__ == "__main__":
    main()
