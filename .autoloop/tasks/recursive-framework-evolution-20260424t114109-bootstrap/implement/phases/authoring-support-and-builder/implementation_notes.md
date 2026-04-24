# Implementation Notes

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: authoring-support-and-builder
- Phase Directory Key: authoring-support-and-builder
- Phase Title: Authoring Support And Builder
- Scope: phase-local producer artifact

## Files changed

- `stdlib/__init__.py`
- `stdlib/validation.py`
- `stdlib/json_artifacts.py`
- `stdlib/contracts.py`
- `runtime/cli.py`
- `workflows/workflow_idea_to_workflow_package/workflow.py`
- `workflows/workflow_idea_to_workflow_package/params.py`
- `workflows/workflow_idea_to_workflow_package/contracts.py`
- `workflows/workflow_idea_to_workflow_package/prompts/build_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/build_verifier.md`
- `workflows/workflow_idea_to_workflow_package/prompts/design_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/design_verifier.md`
- `workflows/workflow_idea_to_workflow_package/prompts/evaluate_producer.md`
- `workflows/workflow_idea_to_workflow_package/prompts/evaluate_verifier.md`
- `workflows/workflow_idea_to_workflow_package/assets/workflow_package_checklist.md`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_workflow_builder_package.py`
- `recursive_autoloop/run_recursive_autoloop.sh`
- `recursive_autoloop/run_recursive_autoloop_templates/bootstrap_task.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/cycle_task.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/framework_evolution_charter.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/framework_roadmap.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/workflow_authoring_doctrine.md.tmpl`
- `recursive_autoloop/run_recursive_autoloop_templates/workflow_examples.md.tmpl`
- `docs/architecture.md`
- `docs/authoring.md`
- `docs/workflows/*.md` restored from `legacy_docs/workflows/*.md`
- `docs/workflows/workflow_idea_to_workflow_package.md`
- `Workflow_Instructions.md`

## Symbols touched

- `ValidationIssue`, `ValidationReport`, `require_non_empty_string`, `require_string_list`, `require_unique_values`, `read_model_file`, `validate_model_file`, `write_model_file`
- `JsonArtifactSpec`
- `review_gate_contracts`, `publication_gate_contracts`
- `runtime.cli._handle_init_workflow`, `runtime.cli._scaffold_workflow`
- `WorkflowIdeaToWorkflowPackage.State.authoring_shape`
- `workflow_idea_to_workflow_package.Parameters.authoring_shape`

## Checklist mapping

- AC-1: added stdlib-only validation, JSON artifact, and route-contract helper modules plus export/tests; root `workflow` shim unchanged.
- AC-2: `autoloop init workflow` now supports `single`, `flow-specs`, and `package`, rooted under `workflows/`, defaulting to `flow-specs`.
- AC-3: builder workflow now accepts a target authoring shape, emits flow-first outputs, and no longer requires manifest/prompt/asset/init clutter unless the selected shape needs it.
- AC-4: scaffold tests cover all three shapes and compile the generated workflows; builder tests cover `single`, `flow_specs`, and `package` outputs.

## Preserved invariants

- Root `workflow` export surface was not widened.
- `workflow.toml` remains metadata-only and optional for the smaller scaffold/builder shapes.
- Runtime still does not special-case `specs.py`; generated `flow.py` imports it explicitly.
- Existing package-oriented builder flow and route grammar remain explicit; no new workflow DSL was introduced.

## Intended behavior changes

- Stdlib now exposes reusable validation and typed JSON helper seams for optional workflow-local support files.
- `validate_model_file(...)` now reports non-object JSON shapes through `ValidationReport.issues` instead of raising.
- CLI scaffolding defaults to the recommended flow-first two-file layout instead of the legacy mandatory package layout.
- The workflow builder carries authoring-shape intent through invocation metadata and can generate `single`, `flow_specs`, or `package` outputs.

## Known non-changes

- No broad recursive-memory baseline document refresh was attempted.
- No repo-wide authoring refactors for existing workflows were attempted.
- No root-shim JSON/Markdown artifact primitives were added.

## Expected side effects

- Canonical `docs/` and `Workflow_Instructions.md` paths exist again by copying the archived `legacy_docs/` content back into the expected locations.
- Recursive wrapper/template text now matches the package CLI contract that existing package-CLI tests enforce.

## Validation performed

- `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/unit/test_stdlib_and_extensions.py tests/runtime/test_package_cli.py tests/runtime/test_workflow_builder_package.py`
- Reviewer blocking feedback `IMP-001` reproduced and fixed with added unit coverage for non-object JSON validation reporting.
- Additional wider check attempted:
  `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/pytest -q tests/runtime/test_compatibility_runtime.py tests/test_architecture_baseline_docs.py`
  Result: `tests/runtime/test_compatibility_runtime.py` passed; `tests/test_architecture_baseline_docs.py` still fails on pre-existing recursive-memory baseline content outside this phase.

## Deduplication / centralization decisions

- Shared string/list/model validation moved into `stdlib/validation.py` instead of staying workflow-local.
- Optional typed JSON artifact handling is now a thin wrapper over the shared validation seam.
- Common review/publication route-contract bundles live in `stdlib/contracts.py`; transitions remain explicit in workflow code.
