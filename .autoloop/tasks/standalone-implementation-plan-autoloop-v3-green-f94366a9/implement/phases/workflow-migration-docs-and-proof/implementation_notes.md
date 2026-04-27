# Implementation Notes

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: implement
- Phase ID: workflow-migration-docs-and-proof
- Phase Directory Key: workflow-migration-docs-and-proof
- Phase Title: Workflow migration, docs, and proof
- Scope: phase-local producer artifact

## Files changed

- Kernel/runtime/stdlib: `core/__init__.py`, `core/validation.py`, `core/workflow_capabilities.py`, `runtime/cli.py`, `runtime/runner.py`, `stdlib/composition.py`, `stdlib/evaluation.py`
- Active docs and working-tree notes: `docs/architecture.md`, `docs/authoring.md`, `docs/workflows/*.md`, `Workflow_Instructions.md`, `cleanup.md`, `recursive_autoloop/run_recursive_autoloop_templates/*.md.tmpl`
- Bundled workflow packages: `workflows/*/contracts.py`, `workflows/*/workflow.py`, `workflows/*/prompts/README.md`, selected prompt files under `workflows/workflow_run_traces_to_optimization_candidates/prompts/`
- Tests: `tests/test_architecture_baseline_docs.py`, `tests/contract/test_engine_contracts.py`, `tests/strictness/test_no_compat.py`, `tests/unit/test_simple_surface.py`, `tests/unit/test_stdlib_and_extensions.py`, `tests/unit/test_validation.py`, and multiple `tests/runtime/*.py` capability/runtime parity suites

## Symbols touched

- Capability/decomposition payload builders in `core.workflow_capabilities`
- Artifact inventory rebinding and simple-workflow validation in `core.validation`
- Child workflow result packaging in `runtime.runner`
- Selected-workflow eval/composition helpers in `stdlib.evaluation` and `stdlib.composition`
- Active workflow `RouteInfo` declarations and prompt README/runtime-contract wording

## Checklist mapping

- Plan milestone 4.1: migrated active bundled workflows off legacy route metadata and updated prompt/docs wording
- Plan milestone 4.2: expanded/updated contract, runtime, strictness, and stdlib proof coverage for canonical route/artifact payloads
- Plan milestone 4.3: completed full-suite pytest and repo-wide removed-term grep verification outside archived `legacy_docs/`

## Assumptions

- `cleanup.md` is an active working-tree note, not an archived request artifact, so it must satisfy the same removed-term grep boundary as other active docs
- Selected-workflow capability payloads should expose authoritative compiled names; user-facing alias recovery belongs in stdlib consumers rather than the payload serializer

## Preserved invariants

- Runtime/provider behavior stays aligned with earlier kernel phases: reserved routes remain mechanically available, child workflow execution stays direct, and provider control contracts keep the `{tag, reason, payload}` shape
- Public workflow consumers can still refer to unique artifact names through stdlib/eval helpers even though authoritative payloads now use qualified names

## Intended behavior changes

- Active workflow/test/docs surfaces no longer mention removed legacy route-contract terminology
- Selected-workflow capability/decomposition snapshots now consistently show normalized reserved routes and qualified artifact identities
- Child workflow result metadata includes canonical keys plus unqualified aliases when the alias is unique

## Known non-changes

- Archived `legacy_docs/` was intentionally left untouched
- Existing Pydantic warnings in `workflow_run_traces_to_optimization_candidates/contracts.py` about `schema` field shadowing remain unchanged

## Expected side effects

- Downstream snapshot/assertion code that depended on pre-normalization step transition tables or unqualified authoritative artifact names must use the updated proof surfaces
- Repo-wide grep checks for removed route-contract vocabulary now stay clean outside archived material

## Validation performed

- `.venv/bin/pytest tests/runtime/test_workspace_and_context.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py tests/strictness/test_no_compat.py tests/unit/test_stdlib_and_extensions.py`
- `.venv/bin/pytest`
- `.venv/bin/pytest tests/test_architecture_baseline_docs.py tests/runtime/test_workflow_run_traces_to_optimization_candidates.py -q`
- `rg -n "RouteContract|route_contracts|route_required_artifacts|route contract|route-contract" . --glob '!legacy_docs/**' --glob '!.git/**' --glob '!**/__pycache__/**'`

## Deduplication / centralization decisions

- Kept authoritative capability payloads strict and centralized alias recovery in stdlib evaluation/composition helpers
- Reused the same active-doc vocabulary boundary across docs, workflow prompt READMEs, recursive templates, and docs-proof tests
