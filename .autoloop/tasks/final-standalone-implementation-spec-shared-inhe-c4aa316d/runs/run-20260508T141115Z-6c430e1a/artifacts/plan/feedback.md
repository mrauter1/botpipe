# Plan ↔ Plan Verifier Feedback

- Replaced the empty planner artifacts with an implementation-ready four-phase plan covering the new shared `autoloop.policy` module, compiler/simple integration, SDK/runtime merge-order alignment, and regression validation. The plan makes the required intentional public API removals explicit (`PolicyOverride`, `root=`, `typed_input=`, raw enum strings) and ties them to concrete files, invariants, and test suites already present in the repo.
