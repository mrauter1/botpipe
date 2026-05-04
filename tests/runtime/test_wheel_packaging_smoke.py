from __future__ import annotations

import json
import subprocess
import sys
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd or REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _venv_bin(venv_dir: Path, name: str) -> str:
    return str(venv_dir / "bin" / name)


def test_built_wheel_installs_cli_and_packaged_workflow_assets(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    _run(
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--wheel-dir",
        str(dist_dir),
        ".",
    )

    wheels = sorted(dist_dir.glob("*.whl"))
    assert wheels, "python -m pip wheel did not produce a wheel"

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pip = _venv_bin(venv_dir, "pip")
    python = _venv_bin(venv_dir, "python")
    autoloop = _venv_bin(venv_dir, "autoloop")

    _run(pip, "install", str(wheels[-1]))

    help_result = _run(autoloop, "--help")
    assert "autoloop" in help_result.stdout

    list_help_result = _run(autoloop, "workflows", "list", "--help")
    assert ".autoloop/workflows/." in list_help_result.stdout

    workspace_root = tmp_path / "empty-workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    list_result = _run(autoloop, "workflows", "list", "--root", str(workspace_root))
    payload = json.loads(list_result.stdout)

    assert any(entry["name"] == "autoloop_v1" for entry in payload)
    assert all(entry["source_root_kind"] == "package" for entry in payload)

    asset_check = _run(
        python,
        "-c",
        "\n".join(
            (
                "from importlib.resources import files",
                "root = files('autoloop') / 'workflows'",
                "manifest = root / 'autoloop_v1' / 'workflow.toml'",
                "prompt = root / 'autoloop_v1' / 'prompts' / 'README.md'",
                "asset = root / 'release_candidate_to_go_no_go' / 'assets' / 'release_decision_package_checklist.md'",
                "assert manifest.is_file(), manifest",
                "assert prompt.is_file(), prompt",
                "assert asset.is_file(), asset",
            )
        ),
    )
    assert asset_check.returncode == 0
