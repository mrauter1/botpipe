# Botlane Rename Plan

## Scope
- Complete the product rename from `autoloop` to `botlane` across package roots, public API symbols, runtime identity, workspace state, generated module namespaces, schemas, docs, examples, fixtures, and packaging metadata.
- Rename `autoloop_optimizer` to `botlane_optimizer`.
- Remove legacy compatibility imports and CLI aliases, but preserve read or migration compatibility for existing `.autoloop` workspaces, `autoloop.yaml` / `autoloop.config`, and persisted `autoloop.*` artifacts during the transition.
- Leave unrelated schema families such as `docloop.*` unchanged unless they are intentionally product-branded elsewhere.

## Current Repo Findings
- `pyproject.toml` still publishes `autoloop-v3-surface`, installs the `autoloop` executable, and discovers only `autoloop*` / `autoloop_optimizer*` packages.
- `autoloop/__init__.py` and `autoloop/sdk.py` still export branded public symbols such as `Autoloop` and `AutoloopSDKError`.
- `autoloop/runtime/cli.py`, `autoloop/runtime/loader.py`, `autoloop/core/workflow_catalog.py`, and related tests hardcode `autoloop`, `.autoloop`, `autoloop.workflows`, and `_autoloop_workspace_workflows`.
- `autoloop/core/schema_registry.py` is the central schema registry, but SDK/runtime serializers and sentinel payloads also embed `autoloop.*` schema and `generated_by` strings outside that file.
- The existing strictness suite excludes live docs and `autoloop/workflows/`, so it currently cannot prove the user-facing rename is complete.

## Interface Contract

### Public Python Surface
- Canonical imports become `import botlane` and `from botlane import ...`.
- Branded public exports become `Botlane`, `BotlaneSDKError`, and `Botlane*` for any other exported Autoloop-prefixed exception, facade, debug helper, or result helper.
- `autoloop` and `autoloop_optimizer` must not remain as deprecated aliases or import shims.

### Runtime And Packaging Surface
- Package roots become `botlane/` and `botlane_optimizer/`.
- Packaging metadata, package discovery, wheel smoke tests, and console entry points must expose `botlane`, not `autoloop`.
- CLI parser identity becomes `prog="botlane"` with Botlane-only help text, command descriptions, package-loading text, and workspace-loading text.
- Machine-facing config and generated identifiers follow the request’s casing policy, including config filenames, sentinel files, marker/header prefixes, and serialized metadata.
- Runtime and config readers continue to accept or migrate legacy `autoloop` inputs during the transition, while all newly written config, package metadata, and generated files use Botlane names only.

### Workspace And Dynamic Import Surface
- Newly written workspace state moves from `.autoloop/` to `.botlane/`.
- Installed workflow modules move from `autoloop.workflows.*` to `botlane.workflows.*`.
- Internal/generated workspace module namespaces move from `_autoloop_workspace_workflows.*` to `_botlane_workspace_workflows.*`.
- Internal runtime/core imports, loader metadata, workflow catalog roots, importlib calls, and `sys.modules` cleanup keys must use the new names consistently.
- Readers and migration paths must still resolve or upgrade existing `.autoloop` workspace inputs during the transition.

### Schema And Artifact Surface
- Product-branded schema IDs for all new writes move from `autoloop.*` to `botlane.*`, including runtime metadata, git tracking, static graphs, topology, optimization artifacts, and SDK task metadata.
- SDK sentinel payloads and `generated_by` markers must also move to Botlane-only strings.
- Persisted `autoloop.*` artifacts remain readable or are migrated during the transition; the rename must not strand existing state.
- Unrelated schema families such as `docloop.*` remain untouched.

## Milestones
1. Rename package roots, packaging metadata, and branded public exports without leaving import aliases behind.
2. Rewrite runtime/CLI/workspace/dynamic-module identity so execution, discovery, and generated state are Botlane-only.
3. Rewrite schemas, workflow packages, docs, examples, fixtures, and embedded source strings to remove remaining live Autoloop references.
4. Prove the break intentionally with wheel/install smoke, negative strictness tests, workspace/schema output checks, and a widened repo grep gate.

## Validation Plan
- Run focused unit/runtime suites around `runtime/cli.py`, `runtime/loader.py`, `core/workflow_catalog.py`, `runtime/workspace.py`, `runtime/static_graph.py`, `runtime/git_tracking.py`, and `sdk.py`.
- Update wheel smoke to prove the built artifact installs `botlane` and the `botlane` executable, and does not expose `autoloop`.
- Add negative tests proving `import autoloop`, `import autoloop_optimizer`, `python -m autoloop`, and the `autoloop` CLI executable all fail or are absent.
- Add generation checks proving scaffolded and runtime-produced workspaces use `.botlane`, generated module namespaces use `_botlane_workspace_workflows`, and emitted schemas use `botlane.*`.
- Add compatibility regression tests proving legacy `.autoloop` workspaces, `autoloop.yaml` / `autoloop.config`, and persisted `autoloop.*` artifacts are still readable or migrated while new writes become Botlane-only.
- Expand the strictness grep test to cover maintained source, workflow packages, tests, docs, examples, and embedded fixture strings. The only non-product exclusions are automation-owned generated state such as `.autoloop/tasks/**`; within the maintained tree, only explicitly named changelog/history files may retain Autoloop text.

## Compatibility Notes
- This is an intentional breaking rename for public package and CLI identity: there is no `autoloop` import alias and no `autoloop` CLI alias.
- Existing `.autoloop` workspaces, `autoloop.yaml` / `autoloop.config`, and persisted `autoloop.*` artifacts must remain readable or be migrated during the transition, even though all new writes become `.botlane`, `botlane.yaml` / `botlane.config`, and `botlane.*`.
- Mixed-brand output generation is not allowed: the transition compatibility requirement is read or migration compatibility only, not continued emission of Autoloop-branded state.
- `python -m autoloop` remains absent because the old package is removed, not because a compatibility stub is introduced.

## Regression Risks
- Partial import-path rewrites can leave loader/catalog/runtime code disagreeing on package roots or module cache keys.
- Schema constants can be updated while serializer literals, sentinel payloads, or generated fixture strings still emit `autoloop.*`.
- Dropping old readers too early can strand existing workspaces, configs, or persisted artifacts even if new Botlane outputs work correctly.
- Docs and embedded workflow source snippets can lag behind code even when tests pass locally.
- Generated packaging outputs such as `build/` and `*.egg-info` can preserve stale branding and create false positives if treated as source of truth.

## Risk Register
- Dynamic import mismatch across `runtime/loader.py`, `core/workflow_catalog.py`, and their tests.
  Control: rename the shared search-root and isolated-namespace contract together, then validate discovery, resolution, and CLI metadata in one slice.
- Mixed schema identity across centralized constants and ad hoc serializers.
  Control: audit both schema registry constants and every `schema` / `generated_by` literal in SDK, runtime, optimizer, and tests before widening grep strictness.
- Compatibility regression for existing users with legacy state.
  Control: keep or add focused readers and migration tests for `.autoloop` workspace inputs, `autoloop.yaml` / `autoloop.config`, and persisted `autoloop.*` payloads while ensuring every new write path emits Botlane names only.
- User-facing examples drifting behind code.
  Control: treat docs, workflow packages, embedded code strings, and fixtures as first-class rename targets rather than cleanup.
- False proof from scanning the wrong tree.
  Control: widen the strictness scan to maintained product files and live docs/examples, explicitly exclude automation-owned `.autoloop/tasks/**`, virtualenvs, caches, and similar generated state, and keep the maintained-tree allowlist limited to explicitly named changelog/history files.

## Rollback
- Roll back by milestone boundary only; do not ship a partially renamed tree.
- If package discovery or runtime loading breaks mid-rename, revert the current slice to the last all-`autoloop` checkpoint before retrying.
- If compatibility tests show old workspace/config/artifact readers broke, restore the reader or migrator before proceeding even if Botlane-only new writes already pass.
- If the strictness gate proves too loose, tighten the allowlist rather than weakening live-tree coverage.
