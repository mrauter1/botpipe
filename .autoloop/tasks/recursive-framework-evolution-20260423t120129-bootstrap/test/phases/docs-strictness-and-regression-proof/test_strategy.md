# Test Strategy

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: docs-strictness-and-regression-proof
- Phase Directory Key: docs-strictness-and-regression-proof
- Phase Title: Harden Docs And Regression Guards
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Maintained docs describe typed provider selection only:
  - `tests/test_architecture_baseline_docs.py` requires `autoloop.yaml`, `autoloop.config`, `provider.name`, `--provider`, `--model`, and `--model-effort` in the maintained docs
- Maintained docs describe canonical resumability:
  - `tests/test_architecture_baseline_docs.py` requires `session_id`, `provider_metadata`, and opaque continuation wording in the maintained docs
  - `tests/strictness/test_no_compat.py` forbids the legacy continuation field token across the maintained live tree
- Recursive execution stays package-CLI-only:
  - `tests/runtime/test_package_cli.py` asserts wrapper/template package-CLI guidance and forbids legacy wrapper tokens and old repo-layout paths
  - `tests/strictness/test_no_compat.py` forbids wrapper legacy mode and legacy flag tokens across the maintained live tree
- Strictness scan scope stays aligned with the phase contract:
  - `tests/strictness/test_no_compat.py` asserts inclusion of `docs/architecture.md`, `docs/authoring.md`, `recursive_autoloop/`, and `tests/`
  - The same test asserts exclusion of `docs/refactor.md` to avoid historical-doc false positives

## Preserved invariants checked

- Strict workflow/runtime shim exports remain unchanged
- Maintained live-tree forbidden-surface scan remains empty
- Full repository test suite stays green after the guard refinements

## Edge cases and failure paths

- Removing either documented config filename from the maintained docs fails the baseline-doc tests
- Reintroducing removed compatibility tokens anywhere in the maintained live tree fails the strictness scan
- Narrowing the strictness scan so maintained docs, recursive assets, or active tests drop out fails the scan-scope test

## Validation

- `.venv/bin/pytest tests/test_architecture_baseline_docs.py tests/strictness/test_no_compat.py`
- `.venv/bin/pytest`

## Known gaps

- Historical docs and task artifacts are intentionally outside this phase’s strictness scan scope
