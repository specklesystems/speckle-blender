from pathlib import Path
from importlib import import_module

import bpy
import sys

print("Starting Speckle Blender installation")
print(sys.executable)

PYTHON_PATH = sys.executable



def modules_path() -> Path:
    modules_path = Path(bpy.utils.script_path_user(), "addons", "modules")
    modules_path.mkdir(exist_ok=True, parents=True)

    # set user modules path at beginning of paths for earlier hit
    if sys.path[1] != modules_path:
        sys.path.insert(1, modules_path)

    return modules_path


print(f"Found blender modules path {modules_path()}")


def is_pip_available() -> bool:
    try:
        import_module("pip")  # noqa F401
        return True
    except ImportError:
        return False


def ensure_pip() -> None:
    print("Installing pip... "),

    from subprocess import run

    completed_process = run([PYTHON_PATH, "-m", "ensurepip"])

    if completed_process.returncode == 0:
        print("Successfully installed pip")
    else:
        raise Exception("Failed to install pip.")


def get_requirements_path() -> Path:
    # we assume that a requirements.txt exists next to the __init__.py file
    path = Path(Path(__file__).parent, "requirements.txt")
    assert path.exists()
    return path


def install_requirements() -> None:
    # set up addons/modules under the user
    # script path. Here we'll install the
    # dependencies
    path = modules_path()
    print(f"Installing Speckle dependencies to {path}")

    from subprocess import run

    completed_process = run(
        [
            PYTHON_PATH,
            "-m",
            "pip",
            "install",
            "-t",
            str(path),
            "-r",
            str(get_requirements_path()),
        ],
        capture_output=True,
        text=True,
    )

    if completed_process.returncode != 0:
        print("Please try manually installing speckle-blender")
        raise Exception(
            """
            Failed to install speckle-blender.
            See console for manual install instruction.
            """
        )


def install_dependencies() -> None:
    # if not is_pip_available():
    #     ensure_pip()

    install_requirements()


def _import_dependencies() -> None:
    import_module("specklepy")
    # the code above doesn't work for now, it fails on importing graphql-core
    # despite that, the connector seams to be working as expected
    # But it would be nice to make this solution work
    # it would ensure that all dependencies are fully loaded  
    # requirements = get_requirements_path().read_text()
    # reqs = [
    #     req.split(" ; ")[0].split("==")[0].split("[")[0].replace("-", "_")
    #     for req in requirements.split("\n")
    #     if req and not req.startswith(" ")
    # ]
    # for req in reqs:
    #     print(req)
    #     import_module("specklepy")


def ensure_dependencies() -> None:
    try:
        _import_dependencies()
        print("Found all dependencies, proceed with loading")
    except ImportError:
        print("Failed to load all dependencies, trying to install them...")
        install_dependencies()
        raise Exception("Please restart Blender.")


if __name__ == "__main__":
    ensure_dependencies()
