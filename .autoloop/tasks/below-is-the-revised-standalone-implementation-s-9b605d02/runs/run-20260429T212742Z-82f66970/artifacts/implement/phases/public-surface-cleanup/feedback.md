# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Canonical Public Surface
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` `workflows/autoloop_v1/workflow.py:46`, `workflows/task_to_workflow_strategy/workflow.py:103`, `workflows/incident_to_hardening_program/workflow.py:127` and the same pattern across the repo’s other simple workflows still call `produce_verify_step(..., writes=[...])`. The new canonical signature rejects `writes`, so package discovery/compilation now fails before execution with `TypeError: produce_verify_step() got an unexpected keyword argument 'writes'`. Repro: `PYTHONPATH=/home/rauter/autoloop_v3_bkp .venv/bin/python` script that resolves and compiles each `workflows/*` package fails for 16 workflow packages with this exact error. Minimal fix: finish the repo workflow migration by replacing each `produce_verify_step(..., writes=...)` with explicit `producer_writes=` / `verifier_writes=` according to actual phase ownership; do not reintroduce a `writes` compatibility alias because the authoritative spec explicitly bans it for this primitive.
- IMP-002 `non-blocking` `docs/authoring.md:75` and `tests/test_architecture_baseline_docs.py:90` still document and assert the removed `Parameters`/`Workflow.Parameters` public authoring model and other stale compatibility vocabulary (`route_infos`, `route_required_outputs`). That does not break the code path above, but it leaves the touched public-surface docs/tests contradicting the canonical `Params` direction recorded for this run. Minimal fix: align the authoring docs and their baseline assertions with the current canonical simple-surface vocabulary in the follow-up phase that cleans the deeper compiler/runtime contract names.
