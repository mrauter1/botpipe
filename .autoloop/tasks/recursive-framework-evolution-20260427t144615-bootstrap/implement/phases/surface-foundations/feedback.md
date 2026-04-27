# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: surface-foundations
- Phase Directory Key: surface-foundations
- Phase Title: Additive Surface Foundations
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `autoloop/__init__.py`, `autoloop/simple.py`, `tests/unit/test_simple_surface.py`: AC-1 is still unmet in a true installed-package-style environment. The new surface only imports when the repo root is also visible (for example via `cwd=/home/rauter/autoloop_v3_bkp/autoloop_v3` or `PYTHONPATH` including that root). With only the installed-package path exposed (`PYTHONPATH=/home/rauter/autoloop_v3_bkp` and a non-repo-root working directory), `import autoloop.simple` still raises `ModuleNotFoundError`. That contradicts the accepted plan’s explicit requirement to keep the exact top-level `autoloop.simple` contract working in installed-package execution mode and to add packaging/distribution glue if a plain subpackage is insufficient. Minimal fix: add a real top-level `autoloop` install/export path that is discoverable when only the installed-package root is present, and extend the subprocess coverage to exercise parent-only `sys.path` from outside the repo root so this compatibility gap cannot regress silently.
