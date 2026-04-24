# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: implement
- Phase ID: resolver-foundation
- Phase Directory Key: resolver-foundation
- Phase Title: Resolver Foundation
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `runtime/loader.py::_is_path_reference` / `resolve_workflow_reference`: bare workflow names are treated as explicit path refs whenever `<root>/<name>` already exists, even if the user meant a canonical workflow name. I confirmed this with a repro where `workflows/demo.py` exists and an unrelated repo-root `demo/` directory causes `resolve_workflow_reference(root, "demo")` to fail with a directory-path error instead of resolving the named workflow. This violates AC-1 and can silently break canonical-name execution in repos that have same-named non-workflow files or directories. Minimal fix: only treat a string as an explicit path when it is syntactically path-like (`/`, `./`, `../`, absolute path, or `.py` suffix), then run canonical-name resolution first for bare names.

- `IMP-002` `blocking` `runtime/loader.py::_resolve_python_path` / `_resolve_parameters_cls`: explicit file and directory refs always pass `package_module_name=None`, so real package paths skip branch 3 of the required parameter precedence and fall through to legacy `params.py`. I confirmed this with a package containing exported `Parameters` in `__init__.py` plus a legacy `params.py`; `resolve_workflow_reference(root, "workflows/pkg")` returns the legacy `params.py` model instead of the package-exported one. That contradicts the accepted five-branch order and means path-based execution is not behaviorally equivalent to module/package execution. Minimal fix: when an explicit path points into a real package under the repo root, derive its package module name and route `_resolve_parameters_cls(...)` through the same package-export lookup before falling back to legacy `params.py`.
