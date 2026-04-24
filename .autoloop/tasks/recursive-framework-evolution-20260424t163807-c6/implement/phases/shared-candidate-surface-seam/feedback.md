# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t163807-c6
- Pair: implement
- Phase ID: shared-candidate-surface-seam
- Phase Directory Key: shared-candidate-surface-seam
- Phase Title: Shared Candidate Surface Seam
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-001 (`blocking`): [stdlib/candidate_surfaces.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/candidate_surfaces.py:77) `materialize_baseline_surface(...)` and [stdlib/candidate_surfaces.py](/home/rauter/autoloop_v3_bkp/autoloop_v3/stdlib/candidate_surfaces.py:224) `validate_candidate_surface_overlay(...)` trust caller-supplied `relative_path` values without rejecting absolute paths or `..` traversal. Concrete failure: a future workflow that passes `../outside.py` in `baseline_relative_paths` or `candidate_manifest["relative_paths"]` will read from outside `repo_root` and write outside `overlay_root`, so the new shared seam silently violates the repo-boundary/path-safety doctrine it is supposed to centralize. Minimal fix: add one shared repo-relative path normalizer in `stdlib/candidate_surfaces.py` and use it before both source and target joins in baseline copy and overlay copy paths, then add negative unit coverage for parent-traversal and absolute-path inputs.
