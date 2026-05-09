# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: implement
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder Reference Graph
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — [artifacts.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/botlane/core/artifacts.py): the phase objective was to unify placeholder parsing/rendering behind the new internal reference layer, but the old runtime placeholder implementation (`_PLACEHOLDER_RE`, `PromptContextView`, `_resolve_placeholder`, `_resolve_ctx_placeholder`, `_resolve_item_placeholder`, `_resolve_worklist_placeholder`, `_resolve_runtime_path`, related helpers) was left in place beside the new implementation in `botlane/core/placeholders.py`. This is substantial duplicated ownership inside the same behavior surface: future placeholder changes can easily update one copy and miss the other, and the restored imports were already needed just to keep the stale copy inert. Minimal fix: remove the dead legacy helpers from `artifacts.py`, or make them thin aliases into `botlane/core/placeholders.py` so there is one canonical runtime placeholder implementation.
- IMP-002 `non-blocking` — [test_placeholder_refs.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/unit/test_placeholder_refs.py): `test_placeholders_module_does_not_import_context_at_runtime` only inspects `ast.ImportFrom` nodes for `context` imports, so it would miss `import botlane.core.context` and similar plain-import forms. The implementation currently satisfies the boundary, but the phase-local guard is weaker than the stated intent. Minimal fix: extend the AST check to cover `ast.Import` nodes and relative/absolute spellings consistently.

- Review cycle 2: `IMP-001` and `IMP-002` appear addressed in the current diff. No new findings identified in the active phase scope.
