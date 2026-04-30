# Plan ↔ Plan Verifier Feedback
- Added a two-phase cleanup plan because the remaining work splits cleanly into maintained core vocabulary removal plus test/strictness quarantine and verification; the repo scan showed `produces` now survives only in core internals, maintained tests/fixtures, and the explicit runtime compatibility suite.
