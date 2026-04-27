# Implementation Notes

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: compatibility-docs-cleanup
- Phase Directory Key: compatibility-docs-cleanup
- Phase Title: Compatibility Migration And Cleanup
- Scope: phase-local producer artifact

## Files changed

- `docs/authoring.md`
- `docs/architecture.md`
- `docs/workflows/*.md` for the public workflow package docs that still taught route-contract wording
- `tests/test_architecture_baseline_docs.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_validation.py`
- `core/validation.py`
- `.autoloop/tasks/recursive-framework-evolution-20260427t144615-bootstrap/decisions.txt`

## Symbols touched

- Public doc vocabulary: `autoloop.simple`, `Route`, `RouteInfo`, `route_infos`, `route_required_outputs`
- Validation: `_validate_route_effects`
- Tests: public-doc token scan, simple-surface export check, `BoardMutation` compile-time rejection

## Checklist mapping

- AC-1: updated `docs/authoring.md`, `docs/architecture.md`, and public workflow docs to teach `autoloop.simple` plus route metadata instead of `RouteContract`
- AC-2: kept bundled workflow/runtime compatibility unchanged while updating tests and docs around the compatibility shims
- Optional cleanup: added compile-time rejection for unsupported `BoardMutation`

## Assumptions

- Keeping `RouteContract` on the strict `workflow` shim is still required for bundled workflow compatibility in this phase
- The untracked `tests/test_architecture_baseline_docs.py`, `tests/unit/test_validation.py`, and `core/validation.py` files are the active working-tree copies for this repository state

## Preserved invariants

- No runtime engine replacement or source-generation path
- Bundled workflows still compile through the legacy compatibility path
- Provider/runtime contract remains deterministic and artifact-governed

## Intended behavior changes

- Public docs no longer teach `RouteContract`, `route_contracts`, or `BoardMutation` as authoring surfaces
- Validation now fails fast when `BoardMutation` is authored instead of deferring to the known runtime trap

## Known non-changes

- The strict `workflow` shim still exports `RouteContract` for compatibility
- Bundled workflows were not rewritten away from legacy `route_contracts` in this phase
- Recursive-memory closeout assertions were not changed; they remain outside this phase scope

## Expected side effects

- Public documentation and doc-pin tests now align with the simple authoring vocabulary and route metadata terminology
- Authors attempting to use `BoardMutation` will now see a compile-time validation error

## Validation performed

- `rg -n "RouteContract|route_contracts|BoardMutation|route-contract|route contracts" docs --glob '*.md'`
- `.venv/bin/python -m pytest tests/test_architecture_baseline_docs.py -k 'not recursive_memory' tests/unit/test_simple_surface.py tests/unit/test_validation.py -q`
- Observed unrelated failures when running the full `tests/test_architecture_baseline_docs.py` slice: three recursive-memory closeout assertions unrelated to this phase

## Deduplication / centralization decisions

- Used one shared runtime-contract phrase in doc-pin tests instead of repeating the legacy `route_contracts` wording
- Applied wording-only replacements across public workflow docs instead of introducing new helper docs or compatibility layers
