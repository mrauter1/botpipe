# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: catalog-and-helper-migration
- Phase Directory Key: catalog-and-helper-migration
- Phase Title: Catalog And Helper Migration
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` `core/workflow_capabilities.py:_inspect_catalog_entry`
  Deep inspection resolves each catalog entry by `entry.workflow_name` instead of by the entry’s origin (`source_path` / manifest-backed module). That breaks the planner decision that canonical names beat aliases and produces incorrect capability payloads when an inferred workflow name collides with another workflow’s alias. Minimal repro: create `workflows/single_review.py` and a manifest package whose alias is `single_review`; `inspect_workflow_capabilities(...)` returns the aliased manifest workflow twice and never reports the single-file workflow. This violates AC-2 and can poison `workflows show`/portfolio helper consumers with the wrong class, source path, parameters, and support files. Fix by inspecting each discovered entry through its exact origin (for example `entry.source_path` or the manifest package’s explicit module), and add a regression test that covers inferred-canonical-name vs manifest-alias collisions.

- Cycle 2 verifier update: `IMP-001` is fixed. Deep inspection now loads manifest-backed catalog entries through their discovered modules and inferred entries through `source_path`, and the new regression test covers the inferred-canonical-name vs manifest-alias collision. No outstanding findings remain in phase scope.
