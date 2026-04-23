# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260423t150056-c1
- Pair: implement
- Phase ID: route-contract-normalization
- Phase Directory Key: route-contract-normalization
- Phase Title: Normalize Route Contracts
- Scope: phase-local authoritative verifier artifact

- IMP-001 [blocking] Import-surface containment is broken across [tests/conftest.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/tests/conftest.py:1), [workflow/__init__.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/workflow/__init__.py:1), and the sibling workspace shim `/home/rauter/autoloop_v3_bkp/workflow/__init__.py`: the new `RouteContract` API is only available under the current test/runtime import path because a non-repo file outside the declared repository root was edited. In this workspace, `import workflow` resolves to the parent shim first, so a clean checkout of `/home/rauter/autoloop_v3_bkp/autoloop_v3` without that external mutation still fails `from workflow import RouteContract` even though the repo-local code compiles. Minimal fix: make the repo own the canonical `workflow` import surface used by tests/runtime, or change the test/runtime import path to resolve the repo-local shim so the phase ships as a self-contained repository change instead of depending on `../workflow/__init__.py`.
