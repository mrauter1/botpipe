# Gap Report

## Original intent considered

- The immutable request in `request.md` required four outcomes: remove active maintained `produces` vocabulary from core runtime/authoring paths, finish the same migration in active non-migration suites, tighten strictness so maintained-tree scans fail on remaining banned vocabulary outside explicit migration fixtures, and remove the redundant `core/__init__.py` alias shim unless one explicit compatibility bridge still had a concrete need.
- The acceptance criteria additionally required the canonical verification suite to keep passing after the cleanup.

## Clarifications / superseding decisions

- `raw_phase_log.md` and `decisions.txt` block 2 explicitly narrowed compatibility scope: executable legacy `PromptStep(..., produces=...)` and `ProduceVerifyStep(..., review_produces=...)` authoring must not survive anywhere in maintained coverage after constructor aliases are removed; compatibility coverage must stay on persisted reader behavior instead.
- `decisions.txt` blocks 3-5 further clarified the bridge and strictness expectations: `core/__init__.py` must stay free of dynamic alias mirroring, the explicit `autoloop_v3.core -> core` bridge may remain if needed by the actual import topology, and the maintained-tree strictness scan must keep `tests/contract/test_engine_contracts.py` inside scope.

## Implemented behavior

- Maintained core code paths are canonicalized. In the final tree, `core/steps.py`, `core/compiler.py`, `core/validation.py`, and `core/engine.py` use `writes`, `producer_writes`, and `verifier_writes`; they no longer expose active `produces`, `review_produces`, or `do_produces` authoring/runtime state.
- Maintained active suites are canonicalized. `tests/unit/test_validation.py`, `tests/contract/test_engine_contracts.py`, `tests/runtime/test_compatibility_runtime.py`, and `tests/fixtures/toy_runtime_workflow.py` no longer author workflows with the removed vocabulary.
- Strictness is tightened as requested. `tests/strictness/test_no_compat.py` now scans the maintained tree, excludes only itself by default, keeps persisted-compatibility exclusions empty, asserts `core/_compat.py` is scanned, and asserts `tests/contract/test_engine_contracts.py` remains in scope.
- The redundant dynamic mirroring is removed from `core/__init__.py`. Compatibility aliasing is centralized in `core/_compat.py`, with thin entrypoint shims in `__init__.py` and `autoloop_v3/core/__init__.py`.
- Evidence from the final tree scan is clean: `rg -n "\\bproduces\\b|review_produces|do_produces" core runtime tests autoloop stdlib workflows docs` only found the strictness self-test patterns plus ordinary English prose, not active maintained workflow declarations.
- Verification passed. The recorded implement/test artifacts report the canonical suite passing, and I independently reran `.venv/bin/python -m pytest tests/unit/test_validation.py tests/contract/test_engine_contracts.py tests/runtime/test_compatibility_runtime.py tests/runtime/test_runtime_static_graph.py tests/runtime/test_provider_backends.py tests/strictness/test_no_compat.py` with result `259 passed`.

## Unresolved gaps

- None.

## Differences justified by later clarification or analysis

- The request asked to remove the redundant alias shim or reduce compatibility to one explicit, justified path. The final tree keeps one shared bridge mechanism in `core/_compat.py`, but two package entrypoints call it: repo-root `__init__.py` and `autoloop_v3/core/__init__.py`. This is justified by the later implementation analysis and tests: the actual import topology exercises both entrypoints, while the alias table itself now lives in one place only and `core/__init__.py` no longer performs dynamic mirroring.

## Recommended next run

- No follow-up implementation run is required for this request.
