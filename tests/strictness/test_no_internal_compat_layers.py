from __future__ import annotations

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
    "\"_route_table\"",
    "_route_table=",
    "_effective_" + "route_table",
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


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.py")))
    return files
