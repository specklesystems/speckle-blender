# speckle-blender

Next-gen Speckle connector for Blender, shipped as a Blender extension. The add-on package
`bpy_speckle/` is the entire product and the only thing `release.yml` zips; `tools/` is the local dev
harness — not shipped, not run in CI.

```
bpy_speckle/
  connector/
    ui/                 panels and dialogs (SPECKLE_PT_*, SPECKLE_OT_*)
    blender_operators/  operator classes bound to UI buttons
    operations/         publish_operation.py, load_operation.py (network orchestration only)
    speckle_api/        the one seam onto the server: client cache + failure policy, account/project/
                        model/version queries, URL resolver. Import from the package, not its modules.
    authentication.py   OAuth-over-localhost account-add flow (stdlib only)
    utils/              property groups, model-card bookkeeping, DUI3 config, display formatting,
                        dialog plumbing — no network
  converter/
    to_speckle/         Blender -> Speckle (per-type modules, scene_to_speckle.py, bundle_exporter.py)
    from_bundle/        specklepy Model -> data-blocks (direct bake)
  installer.py          bootstraps specklepy into the connector install path
tools/                  headless publish harness + synthetic receive tests (tools/README.md)
```

The artifact bundle is the **only** publish and receive path — there is no classic object-graph
fallback. Transport, parsing and send orchestration belong to `specklepy.bundle` (`send()`,
`download_bundle`, `read_bundle`, `Model`, `BundleBuilder`); the connector owns conversion and the
bake — the C# `IBundleBuilder` boundary: "a connector's send is exactly its conversion".
`specklepy[bundle]` + pyarrow are hard requirements checked at add-on registration.

## Instruction docs

Read the matching doc before starting. Most clients auto-load a folder's `AGENTS.md` when working
there; if it is not in your context, read it.

| Doc | Read before |
|---|---|
| `bpy_speckle/converter/AGENTS.md` | any work in `bpy_speckle/converter/` — receive pipeline stages, receive gotchas (K-spaces, materials, SGEO decode, container axes) and bundle gotchas (ids, collection instances, metaballs, properties) |
| `tools/README.md` | adding a fixture or an `EXPECT` key to the harness |

## Dev checkout

- Blender's extensions dir symlinks onto `<repo>/bpy_speckle`, so edits take effect on restart with no
  reinstall. Runtime deps (specklepy, pyarrow, …) live under
  `~/.config/Speckle/connector_installations/Blender <ver>/`, which `ensure_dependencies()` prepends
  to `sys.path` on import. Paths and the specklepy-reinstall command: `/local-dev-setup`.
- `bpy_speckle/requirements.txt` is **gitignored and deliberately absent** in a dev checkout — the
  startup installer skips installation when it is missing. `pyproject.toml` + `uv.lock` are the
  committed truth; `export_dependencies.sh` generates it at package time. Never commit one.

## Validating changes

- Run the headless harness (`/run-fixture-harness`): real conversion + bundle export inside
  `Blender --background`, decoded into assertable text — no GUI, account or server. Receive has its
  own synthetic-bundle tests built with pyarrow, because the publish harness only produces
  Blender-shaped bundles. Prefer this over asking the user to publish manually; reserve the manual
  Blender + viewer check for what the harness cannot cover — the *server* ingesting the bundle and
  the viewer rendering it — once per feature, not per iteration.
- **The harness is local-only by deliberate choice. Do not add it to `.github/workflows/`.** PR CI
  runs pre-commit (ruff) only and stays that way while the bundle format is moving; ruff linting
  `tools/` via `--all-files` is intended — that is linting, not the harness running.
- Fixtures are scenes-as-code in `tools/fixtures/`, never `.blend` blobs, so they diff in review.

## Publish path

`publish_operation()` has exactly one path: convert, then hand a populated `BundleBuilder` to
`specklepy.bundle.send()`.

1. `build_collection_hierarchy` (`converter/to_speckle/scene_to_speckle.py`, Blender → Speckle
   `Collection`) — no network.
2. `BlenderBundleExporter(builder).export(root)` walks the tree onto specklepy's `BundleBuilder`,
   which writes the parquet bundle locally.
3. `send()` owns everything after conversion: creates the ingestion, reads the server's reserved
   version id, renames the files onto it, uploads, and calls `fail_with_error` teardown on any
   exception. `complete` creates the version; version messages are dropped (no field in the payload
   — a server-side API gap), so there is no message input in the UI. The version's
   `referencedObject` is the SDK bundle reference `bundle.<project>.<model>.<version>`.

- `publish_operation` and `load_operation` take every input (account / project / model / version
  ids) as explicit parameters and never read `WindowManager` state — the main-panel and model-card
  flows call them identically. Operators own the `wm.selected_*` lifecycle; operations never touch it.
- Conversion runs entirely before `send()`, so a scene that converts to nothing raises without ever
  creating an ingestion. A server without the /api/v2 data endpoints cannot reserve a version id;
  `send()` raises and the operator surfaces "this server does not support artifact bundles" — no
  fallback.
- The split is what makes offline testing possible: steps 1–2 need no network, and the harness
  finishes them with `builder.build()` instead of `send()`.

## Receive path

`load_operation()` downloads the version's artifact bundle (`specklepy.bundle.download_bundle` →
`read_bundle` + `Model`) and bakes it via `converter/from_bundle/bundle_to_native.bake_bundle` — the
only receive path. A version without a bundle (not yet migrated by the server-side migration
service) is a raised error with an "artifact bundle" message, never a fallback.

Blender takes the **direct-bake** path (Rhino's `IArtifactHostObjectBuilder`), not the
Base-reconstruction path (Revit's): parquet arrays go straight to `bpy.data`, no `Base` graph is
ever built, so dense meshes skip per-object pydantic validation — that is why the raw-array
`sgeo.decode_mesh` exists alongside `sgeo.decode`. Blender construction lives behind the private
`converter/from_bundle/_baking/` package; its layout and the receive gotchas are in
`bpy_speckle/converter/AGENTS.md`.

## Conventions

- Ruff for lint + format, enforced by pre-commit (`uv run pre-commit install`). No test framework —
  the harness in `tools/` fills that role locally.
- `bpy_speckle/__init__.py` carries `bl_info` and registers every class; new operators and panels
  must be added to its registration lists.
- Type-checking against `fake-bpy-module-latest` gives autocomplete only; it cannot evaluate a
  depsgraph, so anything touching modifiers or `to_mesh()` must be exercised through real Blender.

## Agent config (ADR-0008)

Tracked sources: this file, `bpy_speckle/converter/AGENTS.md`, repo-local `agents/skills/`, the
hooks `.claude/settings.json` + `.codex/hooks.json`, and omp's `.omp/extensions/atlas-sync.js`.
`.claude/skills/`, `.agents/skills/`, `.mcp.json`, `.codex/config.toml` and the block below are
written by `../atlas/scripts/sync-agents.py` (session start, `mise run agents-sync` at the atlas
root) — edit the source, never the output. Layout, opt-in shared MCP servers and collision rules:
`../atlas/agents/README.md`.

<!-- atlas:shared:begin -->

<!-- Duplicated from the atlas checkout root AGENTS.md by atlas/scripts/sync-agents.py for clients that stop at this repo's git root (Codex, Grok). Edit the atlas copy. -->

# Code comments: decision significance only

Write a comment only when it states a decision or constraint the code
cannot show — the why behind a non-obvious choice, with the ticket, spec,
or ADR reference when one exists. Never write comments that:

- describe the current state of the world elsewhere ("the chart ignores
  this value for now", "X hasn't landed yet") — they go stale silently
  the moment that other thing changes;
- retell the spec, plan, or PR narrative — reference the ticket instead;
- explain what the next line does.

That context belongs in the commit message, PR body, or ticket. This
policy overrides matching the comment density of the surrounding file:
a legacy heavy-comment file does not license new narrative comments.

# Ticket workflow: claim before you code

When starting implementation of a Linear ticket — via /implement, /tdd, or
no skill at all — first claim it:

1. Move the ticket to **In Progress**.
2. Assign it to the developer running the session (`linear-server`
   `get_user` with query "me").

If the ticket is already In Progress and assigned to someone else, stop
and confirm with the user before touching it — it may be claimed by a
parallel session, and double-resolving a claimed ticket has burned us
before.

This applies only to work tracked as a Linear ticket; untracked work and
repo-local trackers with their own conventions are unaffected. Claiming is
the only transition this rule owns — later states (review, done) belong to
the PR flow.

# Ways of working (Speckle stack)

When the user starts describing a feature, refactor, bug, or plan, suggest
the matching entry point instead of diving into implementation: `/wayfinder`
for big/foggy multi-session work, `/grill-me` (or `/grill-with-docs`) to
stress-test one plan, `/prototype` when "how should it look/behave" is open,
then `/to-spec` → `/to-tickets` → `/implement` (which calls `/code-review`).
The full loop: `atlas/ways-of-working.md` in the speckle-atlas checkout root
(`../atlas/ways-of-working.md` from this repo in the standard nested layout)
— read it before shaping non-trivial work.

Specs: cross-repo → the atlas repo's `atlas/specs/`; local to this repo →
this repo's `specs/` folder. Same structure everywhere: `YYYY-MM-title.md`,
a linked Linear project, worked via PR. Check both places when picking up
spec work.

ADR linking is two-way (atlas ADR-0003 + its amendment): a repo-local ADR
born from a cross-repo project back-links the owning atlas spec in its
header and is indexed from that spec; and when a stack-level ADR — standing
(`atlas/adr/`) or a spec's — governs a specific module of this repo, that
module carries a **pointer ADR** in its local ADR home. A pointer is a thin
stub, never a fork of the atlas content: it keeps the atlas ADR's number and
title, names the atlas text as canonical, links it and its spec by relative
path (never GitHub URLs), summarizes the decision and what it binds in this
module, and is registered in the module's docs index and the repo's context
map. The pointer lands with the work that makes the decision bind the
module. If a pointer's atlas links don't resolve, this checkout is missing
the atlas layer — ask the user to set up the speckle-atlas checkout above
this repo before acting on that decision.

Shared skills, MCP definitions, and conventions change **in the speckle-atlas
repo via PR** — never by editing synced outputs (`.agents/skills`,
`.claude/skills`, `.mcp.json`, `.codex/config.toml`, this block) or forking a
local copy in this repo. A repo-local skill with a shared skill's name fails
the sync (ADR-0008); there is no override.

<!-- atlas:shared:end -->
