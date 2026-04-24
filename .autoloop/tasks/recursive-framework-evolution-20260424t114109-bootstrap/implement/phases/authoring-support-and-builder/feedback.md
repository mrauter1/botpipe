# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: authoring-support-and-builder
- Phase Directory Key: authoring-support-and-builder
- Phase Title: Authoring Support And Builder
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 | blocking | `stdlib/validation.py:84` `validate_model_file(...)` still raises for a JSON file that parses successfully but is not an object, because `_read_json_object(...)` throws `ValueError` and that path is not converted into a `ValidationReport`. Concrete failure: `validate_model_file(path_to_array_json, MyModel)` currently aborts with `ValueError: <file> must contain a JSON object` instead of returning readable validation feedback, which contradicts the new helper contract and breaks callers that expect `validate_*` to be non-throwing. Minimal fix: catch the `_read_json_object(...)` shape error inside `validate_model_file(...)` and translate it into a `ValidationIssue`; keep the shape-validation/report logic centralized in `stdlib/validation.py`.

- IMP-002 | non-blocking | `recursive_autoloop/run_recursive_autoloop.sh`, `recursive_autoloop/run_recursive_autoloop_templates/*.md.tmpl`, `docs/*.md`, and `Workflow_Instructions.md` extend beyond the active phase contract, which explicitly excludes recursive-template wording refresh beyond builder-specific prompts. The changes were enough to satisfy the package-CLI tests, but they also widen the blast radius into the later docs/recursive-memory slices and were not fully brought into parity with `tests/test_architecture_baseline_docs.py`. Minimal fix: keep the builder-facing prompt/checklist/scaffold changes in this phase, but move the broader wrapper/template/docs refresh into its own later slice with dedicated validation.
