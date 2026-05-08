from __future__ import annotations

import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_PRODUCT = "auto" + "loop"
LEGACY_OPTIMIZER = LEGACY_PRODUCT + "_optimizer"
LEGACY_WORKFLOW_V1 = LEGACY_PRODUCT + "_v1"


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
    with zipfile.ZipFile(wheels[-1]) as wheel_archive:
        names = wheel_archive.namelist()

    assert any(name.startswith("botlane/") for name in names)
    assert any(name.startswith("botlane/workflows/botlane_v1/") for name in names)
    assert not any(name.startswith(f"{LEGACY_PRODUCT}/") for name in names)
    assert not any(name.startswith(f"{LEGACY_OPTIMIZER}/") for name in names)

    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pip = _venv_bin(venv_dir, "pip")
    python = _venv_bin(venv_dir, "python")
    botlane = _venv_bin(venv_dir, "botlane")
    legacy_cli = _venv_bin(venv_dir, LEGACY_PRODUCT)

    _run(pip, "install", str(wheels[-1]), cwd=tmp_path)

    assert not Path(legacy_cli).exists()

    help_result = _run(botlane, "--help", cwd=tmp_path)
    assert "botlane" in help_result.stdout
    assert "workflows" in help_result.stdout
    assert "run" in help_result.stdout
    assert LEGACY_PRODUCT not in help_result.stdout

    workflow_help_result = _run(botlane, "workflows", "--help", cwd=tmp_path)
    assert "list" in workflow_help_result.stdout
    assert LEGACY_PRODUCT not in workflow_help_result.stdout

    import_check = _run(
        python,
        "-c",
        "\n".join(
            (
                "import botlane",
                "import importlib.util",
                "import importlib.metadata",
                "from botlane import FINISH, Route, Workflow, step",
                "from botlane.workflows.botlane_v1 import BotlaneV1",
                "from botlane.runtime import cli",
                "scripts = {entry.name: entry.value for entry in importlib.metadata.entry_points(group='console_scripts')}",
                "assert Workflow is not None",
                "assert step is not None",
                "assert Route is not None",
                "assert FINISH == 'FINISH'",
                "assert BotlaneV1.name == 'botlane_v1'",
                "assert 'botlane' in scripts",
                f"assert '{LEGACY_PRODUCT}' not in scripts",
                f"assert importlib.util.find_spec('botlane.workflows.{LEGACY_WORKFLOW_V1}') is None",
                "assert callable(cli.main)",
            )
        ),
        cwd=tmp_path,
    )
    assert import_check.returncode == 0

    old_import_check = subprocess.run(
        [
            python,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    f"importlib.import_module('{LEGACY_PRODUCT}')",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert old_import_check.returncode != 0

    old_optimizer_import_check = subprocess.run(
        [
            python,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    f"importlib.import_module('{LEGACY_OPTIMIZER}')",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert old_optimizer_import_check.returncode != 0

    old_module_run = subprocess.run(
        [python, "-m", LEGACY_PRODUCT],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert old_module_run.returncode != 0


def test_repo_local_editable_install_exposes_only_botlane_cli_identity(tmp_path: Path) -> None:
    repo_venv = REPO_ROOT / ".venv"
    python = Path(_repo_venv_bin("python"))
    pip = Path(_repo_venv_bin("pip"))
    botlane = Path(_repo_venv_bin("botlane"))
    legacy_cli = Path(_repo_venv_bin(LEGACY_PRODUCT))

    if not python.exists() or not pip.exists():
        pytest.skip("repo-local .venv is not present")

    show_botlane = _run(str(pip), "show", "botlane-v3-surface", cwd=tmp_path)
    assert "Name: botlane-v3-surface" in show_botlane.stdout
    assert f"Editable project location: {REPO_ROOT}" in show_botlane.stdout

    show_legacy = subprocess.run(
        [str(pip), "show", "autoloop-v3-surface"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert show_legacy.returncode != 0

    assert botlane.exists()
    assert not legacy_cli.exists()

    help_result = _run(str(botlane), "--help", cwd=tmp_path)
    assert "botlane" in help_result.stdout
    assert LEGACY_PRODUCT not in help_result.stdout

    metadata_check = _run(
        str(python),
        "-c",
        "\n".join(
            (
                "import importlib.metadata",
                "import importlib.util",
                "dist = importlib.metadata.distribution('botlane-v3-surface')",
                "scripts = {entry.name: entry.value for entry in dist.entry_points if entry.group == 'console_scripts'}",
                "assert dist.metadata['Name'] == 'botlane-v3-surface'",
                "assert scripts == {'botlane': 'botlane.runtime.cli:main'}",
                "assert importlib.util.find_spec('botlane') is not None",
                f"assert importlib.util.find_spec('{LEGACY_PRODUCT}') is None",
                "try:",
                "    importlib.metadata.distribution('autoloop-v3-surface')",
                "except importlib.metadata.PackageNotFoundError:",
                "    pass",
                "else:",
                "    raise AssertionError('autoloop-v3-surface is still installed')",
            )
        ),
        cwd=tmp_path,
    )
    assert metadata_check.returncode == 0
