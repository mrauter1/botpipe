from __future__ import annotations

import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest


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


def _repo_venv_bin(name: str) -> str:
    return _venv_bin(REPO_ROOT / ".venv", name)


def test_built_wheel_installs_public_botpipe_package_and_cli(tmp_path: Path) -> None:
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
    with zipfile.ZipFile(wheels[-1]) as wheel_archive:
        names = wheel_archive.namelist()

    assert any(name.startswith("botpipe/") for name in names)
    assert any(name.startswith("botpipe/workflows/botpipe_v1/") for name in names)

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pip = _venv_bin(venv_dir, "pip")
    python = _venv_bin(venv_dir, "python")
    botpipe = _venv_bin(venv_dir, "botpipe")

    _run(pip, "install", str(wheels[-1]), cwd=tmp_path)

    help_result = _run(botpipe, "--help", cwd=tmp_path)
    assert "botpipe" in help_result.stdout
    assert "workflows" in help_result.stdout
    assert "run" in help_result.stdout

    workflow_help_result = _run(botpipe, "workflows", "--help", cwd=tmp_path)
    assert "list" in workflow_help_result.stdout

    import_check = _run(
        python,
        "-c",
        "\n".join(
            (
                "import botpipe",
                "import importlib.util",
                "import importlib.metadata",
                "dist = importlib.metadata.distribution('botpipe')",
                "from botpipe import FINISH, Route, Workflow, step",
                "from botpipe.workflows.botpipe_v1 import BotpipeV1",
                "from botpipe.runtime import cli",
                "scripts = {entry.name: entry.value for entry in dist.entry_points if entry.group == 'console_scripts'}",
                "assert Workflow is not None",
                "assert step is not None",
                "assert Route is not None",
                "assert FINISH == 'FINISH'",
                "assert BotpipeV1.name == 'botpipe_v1'",
                "assert dist.metadata['Name'] == 'botpipe'",
                "assert scripts == {'botpipe': 'botpipe.runtime.cli:main'}",
                "assert callable(cli.main)",
            )
        ),
        cwd=tmp_path,
    )
    assert import_check.returncode == 0


def test_repo_local_editable_install_exposes_only_botpipe_cli_identity(tmp_path: Path) -> None:
    repo_venv = REPO_ROOT / ".venv"
    python = Path(_repo_venv_bin("python"))
    pip = Path(_repo_venv_bin("pip"))
    botpipe = Path(_repo_venv_bin("botpipe"))

    if not python.exists() or not pip.exists():
        pytest.skip("repo-local .venv is not present")

    show_botpipe = _run(str(pip), "show", "botpipe", cwd=tmp_path)
    assert "Name: botpipe" in show_botpipe.stdout
    assert f"Editable project location: {REPO_ROOT}" in show_botpipe.stdout

    assert botpipe.exists()

    help_result = _run(str(botpipe), "--help", cwd=tmp_path)
    assert "botpipe" in help_result.stdout

    metadata_check = _run(
        str(python),
        "-c",
        "\n".join(
            (
                "import importlib.metadata",
                "import importlib.util",
                "dist = importlib.metadata.distribution('botpipe')",
                "scripts = {entry.name: entry.value for entry in dist.entry_points if entry.group == 'console_scripts'}",
                "assert dist.metadata['Name'] == 'botpipe'",
                "assert scripts == {'botpipe': 'botpipe.runtime.cli:main'}",
                "assert importlib.util.find_spec('botpipe') is not None",
            )
        ),
        cwd=tmp_path,
    )
    assert metadata_check.returncode == 0
