# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-standalone-spec-autoloop-v3-explici-7b9dcd08
- Pair: implement
- Phase ID: restore-provider-route-required-writes
- Phase Directory Key: restore-provider-route-required-writes
- Phase Title: Restore Effective Provider Route Maps
- Scope: phase-local authoritative verifier artifact

- `IMP-000` | `non-blocking` | No review findings. The provider-contract builder now exposes effective `route_required_writes` for visible ordinary-step and verifier routes, authored route metadata remains unchanged, branch-group coverage stayed green, and the repository suite passed with `./.venv/bin/python -m pytest -q`.
