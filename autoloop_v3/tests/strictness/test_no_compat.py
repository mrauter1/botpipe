from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "autoloop_v3"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_removed_compat_source_files_do_not_exist() -> None:
    assert not (PACKAGE_ROOT / "workflow" / "compat.py").exists()
    assert not (PACKAGE_ROOT / "workflow" / "observers.py").exists()


def test_runtime_modules_remain_phase_agnostic() -> None:
    runtime_sources = "\n".join(_read(path) for path in sorted((PACKAGE_ROOT / "runtime").rglob("*.py")))

    for forbidden in (
        "autoloop_v1",
        "run_autoloop_v1",
        "activate_next_phase",
        "phase_selected",
        "phase_started",
        "phase_completed",
        "needs_replan",
        "needs_rework",
        "raw_phase_log.md",
        "decisions.txt",
        "plan_session",
        "phase_session",
    ):
        assert forbidden not in runtime_sources
