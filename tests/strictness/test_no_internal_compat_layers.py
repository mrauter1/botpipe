from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "botlane",
    REPO_ROOT / "botlane_optimizer",
)
REMOVED_INTERNAL_TOKENS = (
    "Compiled" + "Workflow",
    "Compiled" + "Step",
    "Compiled" + "Route",
    "Compiled" + "Artifact",
    "Compiled" + "BranchGroupSpec",
    "Compiled" + "BranchStepSpec",
    "plan_" + "adapters",
    "workflow_plan_" + "from_compiled",
    "compiled_" + "workflow_from_plan",
    "step_plan_" + "from_compiled_step",
    "compiled_" + "step_from_step_plan",
    "route_contract_" + "from_compiled",
    "route_contract_" + "from_compiled_route",
    "compiled_" + "route_from_route_contract",
    "_COMPILED_" + "WORKFLOW_CACHE",
    "compile_" + "workflow_plan",
    "_compiled_" + "step",
    "_DirectRuntime" + "Control",
    "RouteFinalization" + "Result",
    "original_" + "step",
)
FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES = frozenset({"_route_table", "_effective_route_table"})
ENGINE_BOUNDARY_FILES = (
    REPO_ROOT / "botlane" / "core" / "engine_collaborators.py",
    REPO_ROOT / "botlane" / "core" / "branch_groups" / "runtime.py",
    REPO_ROOT / "botlane" / "core" / "execution_runtime_services.py",
)
REMOVED_INTERNAL_PATHS = (
    REPO_ROOT / "botlane" / "core" / ("plan_" + "adapters.py"),
)


def test_removed_internal_compatibility_files_are_gone() -> None:
    for path in REMOVED_INTERNAL_PATHS:
        assert not path.exists(), path.relative_to(REPO_ROOT).as_posix()


def test_maintained_python_sources_do_not_reference_removed_internal_compatibility_symbols() -> None:
    violations: list[str] = []

    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for token in REMOVED_INTERNAL_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} contains {token!r}")

    assert violations == []


def test_maintained_python_sources_do_not_reintroduce_step_owned_route_table_symbols() -> None:
    violations: list[str] = []

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            match node:
                case ast.Name(id=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.Attribute(attr=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.Constant(value=name) if isinstance(name, str) and name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.FunctionDef(name=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))
                case ast.AsyncFunctionDef(name=name) if name in FORBIDDEN_STEP_ROUTE_OWNERSHIP_NAMES:
                    violations.append(_symbol_violation(path, node, name))

    assert violations == []


def test_execution_collaborators_do_not_reintroduce_engine_reach_through() -> None:
    violations: list[str] = []

    for path in ENGINE_BOUNDARY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            match node:
                case ast.arg(arg="engine"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces engine constructor/service injection")
                case ast.Attribute(value=ast.Name(id="self"), attr="_engine"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces stored Engine state")
                case ast.Attribute(value=ast.Name(id="engine"), attr=attr) if attr.startswith("_"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces Engine private helper access engine.{attr}")
                case ast.Attribute(value=ast.Attribute(value=ast.Name(id="self"), attr="_engine"), attr=attr) if attr.startswith("_"):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} reintroduces Engine private helper access self._engine.{attr}")

    assert violations == []


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files


def _symbol_violation(path: Path, node: ast.AST, name: str) -> str:
    lineno = getattr(node, "lineno", "?")
    return f"{path.relative_to(REPO_ROOT)}:{lineno} reintroduces forbidden route-ownership symbol {name!r}"
