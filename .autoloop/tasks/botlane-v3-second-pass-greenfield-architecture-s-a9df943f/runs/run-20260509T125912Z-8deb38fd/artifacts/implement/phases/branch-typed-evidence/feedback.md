# Implement ↔ Code Reviewer Feedback

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: implement
- Phase ID: branch-typed-evidence
- Phase Directory Key: branch-typed-evidence
- Phase Title: Branch Typed Evidence
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` [botlane/core/branch_groups/runtime.py:_run_fan_in] The phase switched `FanInMetadata.results` from a mapping-shaped manifest payload to a raw `BranchManifest` object (`results=manifest`). That leaks an internal runtime type through the public `ctx.fan_in.results` surface, which the request explicitly says public users must not need to understand. I reproduced this with a fan-in workflow and observed `type(request.context.fan_in.results).__name__ == "BranchManifest"`. Any existing fan-in Python step or callback that treated `ctx.fan_in.results` as a dict-like payload will now fail or become coupled to an internal class. Minimal fix: keep typed `BranchManifest` authoritative internally, but convert at the public fan-in metadata boundary by setting `FanInMetadata.results` to `manifest.to_dict()` (or another public-neutral mapping view built from the canonical serializer) and add contract coverage for `ctx.fan_in.results`.

- Follow-up review (Cycle 2): `IMP-001` is resolved. `BranchGroupRuntime._run_fan_in(...)` now preserves a mapping-shaped public payload via `manifest.to_dict()`, and `tests/contract/test_branch_group_runtime.py` now asserts the `ctx.fan_in.results` boundary directly. No remaining blocking or non-blocking findings in this review pass.
