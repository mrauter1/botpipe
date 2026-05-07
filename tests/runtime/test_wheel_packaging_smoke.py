from __future__ import annotations

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


def test_built_wheel_installs_public_autoloop_package_and_cli(tmp_path: Path) -> None:
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
    assert "workflows" in help_result.stdout
    assert "run" in help_result.stdout

    workflow_help_result = _run(autoloop, "workflows", "--help")
    assert "list" in workflow_help_result.stdout

    import_check = _run(
        python,
        "-c",
        "\n".join(
            (
                "import autoloop",
                "from autoloop import FINISH, Route, Workflow, step",
                "from autoloop.runtime import cli",
                "assert Workflow is not None",
                "assert step is not None",
                "assert Route is not None",
                "assert FINISH == 'FINISH'",
                "assert callable(cli.main)",
            )
        ),
    )
    assert import_check.returncode == 0
