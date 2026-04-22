# Test Author ↔ Test Auditor Feedback

- Task ID: recursive-framework-evolution-20260422t165825-bootstrap
- Pair: test
- Phase ID: package-cli-and-params
- Phase Directory Key: package-cli-and-params
- Phase Title: Package CLI And Parameters
- Scope: phase-local authoritative verifier artifact

- Added package-CLI regression coverage for canonical-name-vs-alias resolution, ambiguous alias failure, deterministic latest-run selection across multiple runs, and explicit `--run-id` targeting of older runs.
- Recorded the clarified scope boundary in the test strategy so wrapper-local `--pairs` / `--full-auto-answers` behavior is not normalized into the phase contract.

- TST-001 `blocking` — `tests/runtime/test_package_cli.py` reuses the same discovered package names such as `workflows.review_workflow` and `workflows.review`-adjacent fixtures across multiple tests and temp roots, but the runtime loader imports discovered packages by module name via `importlib.import_module(...)` without evicting `sys.modules`. That means later tests can silently reuse stale modules from earlier temp directories instead of the fixture they just wrote, making coverage order-dependent and undermining regression detection. Minimal fix: isolate module names per test or clear the relevant `workflows.*` / `workflows` entries from `sys.modules` in the helper or an autouse fixture before invoking the CLI.
