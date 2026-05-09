from __future__ import annotations

import ast
from pathlib import Path

import botlane.sdk as sdk_module
from botlane.runtime.workspace import STATE_DIRNAME, resolve_task_workspace


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    REPO_ROOT / "botlane",
    REPO_ROOT / "botlane_optimizer",
    REPO_ROOT / "tests",
)
EXCLUDED_SCAN_PATHS = {
    REPO_ROOT / "tests" / "strictness" / "test_no_compat.py",
}
LEGACY_PACKAGE = "auto" + "loop"
LEGACY_OPTIMIZER = LEGACY_PACKAGE + "_optimizer"
LEGACY_STATE_DIR = "." + LEGACY_PACKAGE
LEGACY_SDK_TASK_SCHEMA = LEGACY_PACKAGE + ".sdk_task/v1"
LEGACY_BRANCH_RESULTS_SCHEMA = LEGACY_PACKAGE + ".branch_results/v1"
LEGACY_GENERATED_BY = LEGACY_PACKAGE + ".sdk"


def test_botlane_identity_constants_stay_canonical() -> None:
    assert STATE_DIRNAME == ".botlane"
    assert sdk_module.SDK_TASK_SENTINEL_FILENAME == ".botlane-sdk-task.json"

    sdk_source = (REPO_ROOT / "botlane" / "sdk.py").read_text(encoding="utf-8")
    manifest_source = (REPO_ROOT / "botlane" / "core" / "branch_groups" / "manifest.py").read_text(encoding="utf-8")
    optimizer_source = (REPO_ROOT / "botlane_optimizer" / "optimization.py").read_text(encoding="utf-8")

    assert '"botlane.sdk_task/v1"' in sdk_source
    assert '"generated_by": "botlane.sdk"' in sdk_source
    assert '"botlane.branch_results/v1"' in manifest_source
    assert '".botlane"' in optimizer_source


def test_task_workspace_identity_stays_under_dot_botlane_tasks(tmp_path: Path) -> None:
    task_workspace = resolve_task_workspace(tmp_path, "sdk-demo")

    assert task_workspace.state_root == tmp_path / ".botlane"
    assert task_workspace.tasks_dir == tmp_path / ".botlane" / "tasks"
    assert task_workspace.task_dir == tmp_path / ".botlane" / "tasks" / "sdk-demo"
    assert task_workspace.task_root_rel == Path(".botlane") / "tasks" / "sdk-demo"


def test_active_python_sources_do_not_reintroduce_legacy_product_identity() -> None:
    violations: list[str] = []
    for path in _python_files():
        text = path.read_text(encoding="utf-8")
        for token in (
            LEGACY_PACKAGE,
            LEGACY_OPTIMIZER,
            LEGACY_STATE_DIR,
            LEGACY_SDK_TASK_SCHEMA,
            LEGACY_BRANCH_RESULTS_SCHEMA,
            LEGACY_GENERATED_BY,
        ):
            if token in text:
                violations.append(f"{path.relative_to(REPO_ROOT)} contains {token!r}")

    assert violations == []


def test_botlane_optimizer_imports_reference_botlane_namespace() -> None:
    optimizer_root = REPO_ROOT / "botlane_optimizer"
    observed_botlane_import = False

    for path in sorted(optimizer_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "botlane" or alias.name.startswith("botlane."):
                        observed_botlane_import = True
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "botlane" or module.startswith("botlane."):
                    observed_botlane_import = True

    assert observed_botlane_import is True


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path in EXCLUDED_SCAN_PATHS:
                continue
            files.append(path)
    return files
