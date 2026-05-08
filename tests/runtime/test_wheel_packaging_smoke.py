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


def test_built_wheel_installs_public_botlane_package_and_cli(tmp_path: Path) -> None:
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
    botlane = _venv_bin(venv_dir, "botlane")
    autoloop = _venv_bin(venv_dir, "autoloop")

    _run(pip, "install", str(wheels[-1]))

    assert not Path(autoloop).exists()

    help_result = _run(botlane, "--help")
    assert "botlane" in help_result.stdout
    assert "workflows" in help_result.stdout
    assert "run" in help_result.stdout

    workflow_help_result = _run(botlane, "workflows", "--help")
    assert "list" in workflow_help_result.stdout

    import_check = _run(
        python,
        "-c",
        "\n".join(
            (
                "import botlane",
                "import importlib.util",
                "from botlane import FINISH, Route, Workflow, step",
                "from botlane.workflows.botlane_v1 import BotlaneV1",
                "from botlane.runtime import cli",
                "assert Workflow is not None",
                "assert step is not None",
                "assert Route is not None",
                "assert FINISH == 'FINISH'",
                "assert BotlaneV1.name == 'botlane_v1'",
                "assert importlib.util.find_spec('botlane.workflows.autoloop_v1') is None",
                "assert callable(cli.main)",
            )
        ),
    )
    assert import_check.returncode == 0

    old_import_check = subprocess.run(
        [
            python,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "importlib.import_module('autoloop')",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert old_import_check.returncode != 0

    old_optimizer_import_check = subprocess.run(
        [
            python,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "importlib.import_module('autoloop_optimizer')",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert old_optimizer_import_check.returncode != 0

    old_module_run = subprocess.run(
        [python, "-m", "autoloop"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert old_module_run.returncode != 0
