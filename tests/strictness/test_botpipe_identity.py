from __future__ import annotations

import ast
from pathlib import Path

import botpipe.sdk as sdk_module
from botpipe.runtime.workspace import STATE_DIRNAME, resolve_task_workspace


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_botpipe_identity_constants_stay_canonical() -> None:
    assert STATE_DIRNAME == ".botpipe"
    assert sdk_module.SDK_TASK_SENTINEL_FILENAME == ".botpipe-sdk-task.json"

    sdk_source = (REPO_ROOT / "botpipe" / "sdk.py").read_text(encoding="utf-8")
    manifest_source = (REPO_ROOT / "botpipe" / "core" / "branch_groups" / "manifest.py").read_text(encoding="utf-8")
    optimizer_source = (REPO_ROOT / "botpipe_optimizer" / "optimization.py").read_text(encoding="utf-8")

    assert '"botpipe.sdk_task/v1"' in sdk_source
    assert '"generated_by": "botpipe.sdk"' in sdk_source
    assert '"botpipe.branch_results/v1"' in manifest_source
    assert '".botpipe"' in optimizer_source


def test_task_workspace_identity_stays_under_dot_botpipe_tasks(tmp_path: Path) -> None:
    task_workspace = resolve_task_workspace(tmp_path, "sdk-demo")

    assert task_workspace.state_root == tmp_path / ".botpipe"
    assert task_workspace.tasks_dir == tmp_path / ".botpipe" / "tasks"
    assert task_workspace.task_dir == tmp_path / ".botpipe" / "tasks" / "sdk-demo"
    assert task_workspace.task_root_rel == Path(".botpipe") / "tasks" / "sdk-demo"


def test_botpipe_optimizer_imports_reference_botpipe_namespace() -> None:
    optimizer_root = REPO_ROOT / "botpipe_optimizer"
    observed_botpipe_import = False

    for path in sorted(optimizer_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "botpipe" or alias.name.startswith("botpipe."):
                        observed_botpipe_import = True
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "botpipe" or module.startswith("botpipe."):
                    observed_botpipe_import = True

    assert observed_botpipe_import is True
