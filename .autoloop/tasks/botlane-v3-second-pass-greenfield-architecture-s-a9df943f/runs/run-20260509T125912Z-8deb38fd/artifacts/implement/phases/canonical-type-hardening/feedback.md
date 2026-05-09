# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: canonical-type-hardening
- Phase Directory Key: canonical-type-hardening
- Phase Title: Canonical Type Hardening
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [botlane/core/branch_groups/manifest.py], [botlane/core/branch_groups/outcomes.py], [botlane/core/branch_groups/runtime.py]: `build_branch_manifest(...)` now returns `BranchManifest`, but the existing runtime still passes that object into helpers that assume `Mapping` semantics (`manifest.get(...)`, `dict(manifest)`). This crashes normal branch execution and fan-in flows with `AttributeError: 'BranchManifest' object has no attribute 'get'` and `TypeError: 'BranchManifest' object is not iterable`. Concrete failures are reproducible with `.venv/bin/python -m pytest tests/contract/test_async_step_dispatcher.py -q` and `.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py -q`. Minimal fix: centralize the typed-manifest boundary by updating `select_branch_group_outcome(...)` and the fan-in metadata assembly in `branch_groups/runtime.py` to accept `BranchManifest` directly (or convert with `to_dict()` exactly at those call sites) so runtime behavior stays intact while the phase introduces the typed manifest shape.
