# Plan ↔ Plan Verifier Feedback

- Replaced the empty planner artifacts with a five-phase implementation plan centered on one generic engine observer seam, runtime-owned session payload serialization, and a split of `autoloop_v1_support.py` into tiny workflow-owned conventions plus an observer-driven parity harness.
- Captured the main non-obvious constraints explicitly: `parse_phase_ids` should move into `autoloop_v1.py`, exact `phase_dir_key` should stay workflow-owned in a shared conventions helper, and cycle/attempt tracking should stay in parity observer state with resume-time reconstruction from persisted parity artifacts instead of provider session metadata.
