import sys
from pathlib import Path


def patch_installer(tag):
    """Patches the installer with the correct connector version and specklepy version"""
    iss_file = "speckle-sharp-ci-tools/blender.iss"
    iss_path =  Path(iss_file)
    lines = iss_path.read_text().split("\n")
    lines.insert(12, f'#define AppVersion "{tag.split("-")[0]}"')
    lines.insert(13, f'#define AppInfoVersion "{tag}"')

    iss_path.write_text("\n".join(lines))
    print(f"Patched installer with connector v{tag}")


if __name__ == "__main__":
    tag = sys.argv[1]
    patch_installer(tag)