---
name: local-dev-setup
description: Set up or repair a speckle-blender dev checkout — symlink the add-on into Blender's extensions dir, locate the runtime dependency path, reinstall a local specklepy build into it.
---

# Local dev setup

The add-on is used from the working tree via a symlink, so edits take effect on Blender restart
with no reinstall:

```
~/Library/Application Support/Blender/4.3/extensions/user_default/speckle_blender_addon
  -> <repo>/bpy_speckle
```

(Adjust the Blender version segment and, on Linux/Windows, the extensions root to the platform's
user-default extensions directory.)

Runtime dependencies (specklepy, pyarrow, …) live in
`~/.config/Speckle/connector_installations/Blender <ver>/`, installed with Blender's bundled
Python. Importing `bpy_speckle` runs `ensure_dependencies()`, which prepends that directory to
`sys.path` — the headless harness inherits the same path, so there is no separate test environment
to drift.

`bpy_speckle/requirements.txt` is gitignored and deliberately absent in a dev checkout; the startup
installer skips installation when it is missing. `pyproject.toml` + `uv.lock` are the committed
truth and `export_dependencies.sh` generates the requirements file at package time. Never commit
one.

## Reinstall a local specklepy checkout

After changing a local specklepy checkout, reinstall it into the deps path:

```bash
pip install --no-deps -t "~/.config/Speckle/connector_installations/Blender 4.3" <specklepy repo>
```

Then restart Blender (or re-run the harness).
