# Botlane No-Compat Follow-up

## Objective
Finish the Botlane rename as a real behavior removal, not a literal-text cleanup. After this work, only `botlane` and `botlane_optimizer` remain supported, only `.botlane` is a valid runtime state/workspace root, only `botlane.*` schemas remain readable, and only `__botlane_simple_flow_spec__` is recognized.

## Confirmed Legacy Surfaces
- Runtime root detection still accepts `.autoloop/workflows` in [botlane/core/context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/context.py:649) and [botlane/core/workflow_capabilities.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/workflow_capabilities.py:943).
- Workflow catalog still exposes legacy workspace roots in [botlane/core/workflow_catalog.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/workflow_catalog.py:14).
- Runtime state/config fallbacks still read legacy names in [botlane/runtime/workspace.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/runtime/workspace.py:23), [botlane/runtime/config.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/runtime/config.py:28), [botlane/sdk.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/sdk.py:72), [botlane_optimizer/optimization.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane_optimizer/optimization.py:70), and [botlane_optimizer/candidate_surfaces.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane_optimizer/candidate_surfaces.py:534).
- Legacy schema and sentinel compatibility still exist in [botlane/core/discovery.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/discovery.py:434), [botlane/core/schema_registry.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/schema_registry.py:8), [botlane/core/operations.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/operations.py:844), and [botlane/workflows/botlane_v1/parity.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/workflows/botlane_v1/parity.py:22).
- The strictness suite still hides legacy names behind concatenation and still has legacy-behavior tests outside the one intended allowlisted file in [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:133), [tests/runtime/test_workspace_and_context.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workspace_and_context.py:1194), [tests/runtime/test_workflow_catalog_roots.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_workflow_catalog_roots.py:239), and [tests/unit/test_sdk_facade.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_sdk_facade.py:1183).

## Implementation Milestones
### 1. Remove production compatibility behavior
- Update `botlane/core/context.py` and `botlane/core/workflow_capabilities.py` so repo/workspace root inference accepts only `botlane/workflows`, `.botlane/workflows`, and `workflows`.
- Update `botlane/core/discovery.py` so `_is_simple_flow_spec()` recognizes only `__botlane_simple_flow_spec__`.
- Remove legacy state-root/config/schema/header helpers and constants from runtime/optimizer/catalog code instead of renaming them in place. The change set is expected to touch `botlane/runtime/workspace.py`, `botlane/runtime/config.py`, `botlane/core/workflow_catalog.py`, `botlane/core/schema_registry.py`, `botlane/core/operations.py`, `botlane/sdk.py`, `botlane/workflows/botlane_v1/parity.py`, `botlane_optimizer/optimization.py`, and `botlane_optimizer/candidate_surfaces.py`.
- Invariant: no maintained production code may construct Autoloop names indirectly via concatenation, adjacency, joins, or helper constants.

### 2. Rewrite strictness and negative-behavior tests around the new contract
- Move all intentional legacy literals to `tests/strictness/test_no_compat.py` as explicit string constants, not concatenations.
- Add an AST-aware hidden-construction scanner in `tests/strictness/test_no_compat.py` that catches split literals, adjacent literals, and constant-building patterns recreating `autoloop`, `.autoloop`, `autoloop_optimizer`, `_autoloop_workspace_workflows`, and `__autoloop_simple_flow_spec__`.
- Remove `.autoloop` from default scan ignores and keep the historical allowlist exact to `legacy_docs/*.md`.
- Replace existing tests that assert legacy `.autoloop` behavior with negative tests:
  - `.autoloop/workflows/...` is not a recognized workspace marker.
  - `.botlane/workflows/...` still resolves correctly.
  - `__autoloop_simple_flow_spec__` is ignored.
  - `__botlane_simple_flow_spec__` still works.
  - `autoloop` and `autoloop_optimizer` imports and CLI entrypoints remain absent.
- Rewrite or delete legacy-positive tests in runtime/catalog/SDK suites that currently require fallback reads from `.autoloop`.

### 3. Re-audit maintained content and run smoke validation
- Run literal scans for `autoloop`, `Autoloop`, `AUTOLOOP`, `.autoloop`, `autoloop_optimizer`, `autoloop_v3`, `autoloop-v3`, `_autoloop_workspace_workflows`, and `__autoloop_simple_flow_spec__` across maintained source, tests, docs, packaging, scripts, templates, and generated examples.
- Run the hidden-construction scan across maintained Python files and confirm only `tests/strictness/test_no_compat.py` and explicit `legacy_docs/*.md` references remain.
- Execute validation at minimum with `python -m pytest`, import smoke for `botlane` and `botlane_optimizer`, negative import smoke for `autoloop` and `autoloop_optimizer`, `botlane --help`, and existing wheel/package smoke coverage.

## Interface And Compatibility Notes
- Intentional behavior break: `.autoloop` is no longer a readable or discoverable runtime/workflow root anywhere in production code.
- Intentional behavior break: legacy config filenames, legacy schema aliases, legacy SDK sentinels, and legacy replay payload identifiers stop being accepted.
- Intentional behavior break: Botlane-v1 parity logic must no longer parse Autoloop decision headers unless the user later supplies an explicit clarification authorizing historical runtime compatibility.
- No new migration layer, alias package, warning path, or fallback reader may be introduced.

## Regression Controls
- Keep `.botlane` state-root creation, `workflows/` repo discovery, package-installed workflow discovery, and `botlane` CLI help behavior covered by existing tests after the legacy assertions are removed.
- Prefer deleting legacy helper functions/constants over leaving dead compatibility shims that future code can accidentally reuse.
- Verify packaging metadata still exposes only the `botlane` console script and never `autoloop`.

## Risk Register
- `Runtime regression`: removing `readable_state_roots()` and related fallbacks can break resume/history/cleanup flows if callers still assume dual roots. Mitigation: update all callers in the same slice and add negative resume/history tests.
- `Scan false negatives`: a literal-only grep will miss adjacent-string and constant-based reconstruction. Mitigation: use AST/string-node analysis in the strictness suite and keep one explicit allowlisted file for legacy literals.
- `Historical doc bleed`: broad path ignores can hide regressions under active directories. Mitigation: keep only exact `legacy_docs/*.md` allowlist entries and scan the rest of the repo root.

## Rollback
- Revert the compat-removal slice as one unit if Botlane-only runtime behavior unexpectedly breaks package discovery, resume flows, or packaging smoke tests.
- Do not reintroduce partial compatibility fallbacks during rollback; either keep the greenfield Botlane contract or revert to the pre-change baseline cleanly.
