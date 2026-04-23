# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t173132-c4
- Pair: implement
- Phase ID: workflow-catalog-seam
- Phase Directory Key: workflow-catalog-seam
- Phase Title: Workflow Catalog Seam
- Scope: phase-local producer artifact

## Files changed

- `core/workflow_catalog.py`
- `runtime/loader.py`
- `runtime/__init__.py`
- `stdlib/portfolio.py`
- `stdlib/__init__.py`
- `docs/authoring.md`
- `tests/runtime/test_compatibility_runtime.py`
- `tests/unit/test_stdlib_and_extensions.py`
- `tests/test_architecture_baseline_docs.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t173132-c4/decisions.txt`

## Symbols touched

- `core.workflow_catalog.WorkflowCatalogEntry`
- `core.workflow_catalog.discover_workflow_catalog`
- `runtime.loader.discover_workflow_catalog`
- `runtime.loader.discover_workflow_packages`
- `stdlib.portfolio.write_workflow_portfolio_snapshot`
- `autoloop_v3.stdlib.write_workflow_portfolio_snapshot`

## Checklist mapping

- Phase 1 shared catalog seam: implemented via `core/workflow_catalog.py` and the `runtime.loader` reuse path.
- Phase 1 workflow-local portfolio snapshot helper: implemented via `stdlib/portfolio.py` and `stdlib/__init__.py`.
- Phase 1 docs and unit coverage: implemented in `docs/authoring.md`, `tests/runtime/test_compatibility_runtime.py`, `tests/unit/test_stdlib_and_extensions.py`, and `tests/test_architecture_baseline_docs.py`.
- Plan phases 2 and 3 workflow-package shipping / recursive memory closeout: intentionally not touched in this phase-local turn.

## Assumptions

- The live repo-root package layout (`core/`, `runtime/`, `stdlib/`, `workflows/`) remains authoritative over the retired `src/autoloop/...` references in older recursive templates.
- Workflow portfolio docs continue to live under `docs/workflows/` by package name when present.

## Preserved invariants

- `workflow.toml` remains metadata-only; no new manifest fields were added.
- No public CLI behavior or runtime-owned routing behavior was introduced.
- Existing runtime loader APIs for package discovery and resolution remain available.

## Intended behavior changes

- Runtime and authoring code can now share one pure workflow-catalog discovery seam with linked code/doc paths.
- Workflow authors can publish `workflow_portfolio_snapshot.json` (or another workflow-local JSON path) without scraping the repo ad hoc.

## Known non-changes

- No automatic workflow routing, composition, or child execution was added.
- No new workflow package was implemented in this phase.
- `.autoloop_recursive/` standing memory files were not updated because this turn is phase-local to `workflow-catalog-seam`.

## Expected side effects

- `runtime.__init__` now re-exports the additive catalog entry type and discovery helper.
- Portfolio-routing workflows can depend on a stable JSON snapshot shape for current package metadata and linked file paths.

## Validation performed

- `.venv/bin/python -m compileall core/workflow_catalog.py stdlib/portfolio.py runtime/loader.py runtime/__init__.py stdlib/__init__.py tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py tests/test_architecture_baseline_docs.py`
- `.venv/bin/pytest tests/runtime/test_compatibility_runtime.py tests/unit/test_stdlib_and_extensions.py tests/test_architecture_baseline_docs.py`

## Deduplication / centralization decisions

- Centralized manifest parsing and linked-path discovery in `core/workflow_catalog.py` instead of duplicating repo scraping in future portfolio workflows.
- Kept workflow-local JSON writing in `stdlib` rather than moving any portfolio policy into runtime-owned code.
