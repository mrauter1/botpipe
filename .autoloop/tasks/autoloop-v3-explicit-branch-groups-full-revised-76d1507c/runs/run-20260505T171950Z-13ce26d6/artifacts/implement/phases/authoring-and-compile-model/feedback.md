# Implement ↔ Code Reviewer Feedback

- Task ID: autoloop-v3-explicit-branch-groups-full-revised-76d1507c
- Pair: implement
- Phase ID: authoring-and-compile-model
- Phase Directory Key: authoring-and-compile-model
- Phase Title: Authoring And Compile Model
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 [blocking] `autoloop/core/discovery.py::_lower_simple_default_routes` and `autoloop/simple.py::_BranchGroupDeclaration`: branch groups without `fan_in` currently expose `done` / `partial` in `available_routes` but do not compile destinations for them, because the synthetic implicit `question` / `failed` routes make the generic default-route logic think the composite already has authored routing. Repro: a workflow with `parallel(branches={...})` followed by a normal next step compiles `available_routes=('done', 'partial', 'question', 'failed')` while `compiled.routes['<group>']` only contains `question` and `failed`, so a successful mechanical outcome has no route target to follow. This breaks AC-1 and creates a compile/runtime contract mismatch for the no-`fan_in` path. Minimal fix: centralize no-`fan_in` outcome route materialization in the branch-group lowering path so the composite always gets deterministic external transitions for `done` and `partial` in addition to the control routes, instead of relying on the generic simple-step default-route inference around synthetic implicit routes.
