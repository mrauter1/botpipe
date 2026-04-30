# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-standalone-implementation-spec-for-b066b1fd
- Pair: implement
- Phase ID: compatibility-bridge-removal
- Phase Directory Key: compatibility-bridge-removal
- Phase Title: Remove Compatibility Bridges
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 `blocking` — Maintained tests still import dead `autoloop_v3.runtime` / `autoloop_v3.extensions` / `autoloop_v3.workflows` module paths, so the regression surface remains broken even after the `autoloop_v3.core` bridge removal. Concrete examples: [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:8), [tests/runtime/test_compatibility_runtime.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/runtime/test_compatibility_runtime.py:20), and [tests/unit/test_stdlib_and_extensions.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_stdlib_and_extensions.py:55) still import `autoloop_v3.runtime.*`, `autoloop_v3.extensions.*`, `autoloop_v3.stdlib.*`, or `autoloop_v3.workflows.*`, but the corresponding `autoloop_v3/` directories only contain `__pycache__` files and `python3` import checks already fail with `ModuleNotFoundError` for `autoloop_v3.runtime.config`, `autoloop_v3.runtime.loader`, `autoloop_v3.extensions.session_paths`, and `autoloop_v3.workflows.task_to_workflow_strategy`. Failure scenario: in any clean environment with project deps installed, these maintained tests fail during module import before they can validate the removed bridge behavior, so AC-2 is not actually satisfied across the maintained regression surface. Minimal fix: finish canonicalizing the maintained tests/fixtures and embedded source snippets to `runtime`, `extensions`, `stdlib`, and `workflows` root packages, or intentionally restore those `autoloop_v3.*` namespace modules if they are still meant to be supported.

- IMP-002 `non-blocking` — [tests/unit/test_simple_surface.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_simple_surface.py:35) now carries explicit `autoloop_v3.core` failure assertions even though the phase contract and plan said only strictness coverage should continue to mention the removed bridge. This is not an immediate correctness bug, but it duplicates compatibility-removal coverage across strictness and unit layers and increases future maintenance drift. Minimal fix: keep bridge-failure assertions centralized in [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py) and keep `test_simple_surface.py` focused on canonical public API behavior.

## Cycle 2 Re-review

- No new findings. Re-review confirmed that IMP-001 and IMP-002 were addressed: maintained tests/workflows no longer import dead `autoloop_v3.*` runtime/extension/workflow/optimizer namespaces, `core/workflow_capabilities.py` no longer falls back to deleted `autoloop_v3.runtime.loader`, and only [tests/strictness/test_no_compat.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/strictness/test_no_compat.py:134) intentionally references `autoloop_v3.core` for the required failed-import assertion.
