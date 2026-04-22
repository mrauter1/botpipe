# Test Strategy

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: docs-tests-and-legacy-removal
- Phase Directory Key: docs-tests-and-legacy-removal
- Phase Title: Docs Tests And Legacy Removal
- Scope: phase-local producer artifact

## Behavior-to-Test Coverage Map

- Docs and contract rewrite:
  `tests/test_architecture_baseline_docs.py` asserts the docs describe `core`, repo-root `workflows/`, package-based `autoloop`, `messages.jsonl`, `wf_<workflow_name>`, `ctx.invoke_workflow(...)`, and omit legacy raw-target/public-compat text.
- Strict public-surface removal:
  `tests/strictness/test_no_compat.py` asserts the root `workflow` shim stays strict, `workflow.primitives` exports only core primitives, `workflows` does not re-export helper harnesses, and `autoloop_v3.runtime` does not re-export raw loader/runner surfaces.
- Package discovery and loader behavior:
  `tests/runtime/test_compatibility_runtime.py` covers metadata-only discovery, required package `__init__.py` exports, imported main-workflow classes, cross-root cache isolation, same-root class identity stability, legacy config filename rejection, and `runtime.intent_mode` rejection.
- Workspace/message model and subworkflow invariants:
  `tests/runtime/test_workspace_and_context.py` covers task -> workflow -> runs layout, task `messages.jsonl`, immutable run `request.md` snapshots, placeholder resolution, class- and name-based child workflow invocation, and parent/child metadata.
- Package CLI and workflow parameter contract:
  `tests/runtime/test_package_cli.py` covers package-only commands, deterministic latest-run resolution, `-wf` parsing/validation, explicit `--run-id` targeting, and absence of raw public targeting.
- Parity, git scope, and trace locality:
  `tests/runtime/test_workflow_integration_parity.py` and `tests/runtime/test_optional_extensions.py` cover Autoloop-v1 package parity, workflow-folder git tracking, and run-local trace behavior.
- Adjacent API/contract preservation:
  `tests/contract/test_engine_contracts.py`, `tests/unit/test_primitives_and_stores.py`, `tests/unit/test_stdlib_and_extensions.py`, and `tests/unit/test_validation.py` guard the strict authoring surface and related runtime/store invariants touched by the cleanup.

## Preserved Invariants Checked

- Explicit workflow `root` remains authoritative across different repositories in one Python process.
- Repeated resolution inside the same repository preserves workflow class identity.
- Task message persistence stays append-only at task scope; run snapshots stay immutable and run-local.
- Legacy helper harnesses and raw runtime public entrypoints remain absent.

## Edge Cases and Failure Paths

- Ambiguous aliases and broken workflow package exports fail deterministically.
- Legacy `superloop.*` config filenames are ignored rather than silently accepted.
- Legacy `runtime.intent_mode` is rejected instead of being normalized.
- Cross-root `workflows.*` import cache leakage is treated as a regression.

## Flake Risk and Stabilization

- Temporary workflow-package tests clear `workflows.*` modules before and after multi-root assertions so import cache state is deterministic.
- CLI latest-run coverage uses explicit fixture setup instead of sleeps or timestamp mutation.

## Known Gaps

- None within this phase scope; the suite exercises the changed docs/tests/legacy-removal behavior and the adjacent loader regression fixed during implement re-review.
