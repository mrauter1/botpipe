"""Isolated, durable execution of one workflow evaluation trial."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .processes import run_bounded_process
from .trial_models import TrialCase, TrialResult, TrialSettings


def run_trial(
    *,
    code_root: Path,
    workflow_reference: str,
    case: TrialCase,
    fixture_root: Path | None,
    output_root: Path,
    settings: TrialSettings,
    provider_config: dict,
    policy: dict | None = None,
    process_runner=None,
    provider_factory: str | None = None,
) -> TrialResult:
    """Run or resume one trial in its own process and mutable workspace.

    ``output_root`` is the durable identity of the trial. Reusing it requires the
    same inputs and resumes the same Botpipe run, workspace, and provider state.
    """

    root = Path(code_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("code_root must be a directory")
    if not isinstance(workflow_reference, str) or not workflow_reference.strip():
        raise ValueError("workflow_reference must be non-empty")
    requested_destination = Path(output_root).expanduser()
    if requested_destination.is_symlink():
        raise ValueError("output_root must not be a symlink")
    destination = requested_destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fixture = None if fixture_root is None else Path(fixture_root).resolve(strict=True)
    if fixture is not None and not fixture.is_dir():
        raise ValueError("fixture_root must be a directory")
    if case.workspace == "fixture" and fixture is None:
        raise ValueError("fixture workspace requires fixture_root")
    if case.assets and fixture is None:
        raise ValueError("case assets require fixture_root")

    identity = {
        "schema": "botpipe.workflow-trial.v1",
        "code_root": str(root),
        "code_tree_sha256": _tree_digest(root),
        "workflow_reference": workflow_reference,
        "case": case.model_dump(mode="json"),
        "fixture_root": None if fixture is None else str(fixture),
        "fixture_tree_sha256": None if fixture is None else _tree_digest(fixture),
        "settings": settings.model_dump(mode="json"),
        "provider_config": provider_config,
        "policy": policy,
        "provider_factory": provider_factory,
    }
    encoded_identity = _json_bytes(identity)
    digest = hashlib.sha256(encoded_identity).hexdigest()
    run_id = f"trial-{digest[:32]}"
    task_id = f"trial-{case.case_id}"[:128]
    manifest_path = destination / "trial.json"
    workspace = destination / "workspace"
    state_dir = destination / "state"
    if manifest_path.is_file():
        recorded = _read_bounded(manifest_path, settings.max_output_bytes)
        if recorded != identity:
            raise ValueError("output_root already belongs to a different trial")
        if not workspace.is_dir() or not state_dir.is_dir():
            raise RuntimeError("existing trial is missing its workspace or state")
    else:
        if destination.exists():
            # New roots publish atomically, so a nonempty root without its
            # manifest has no ownership proof and must never be deleted.
            if not destination.is_dir() or any(destination.iterdir()):
                raise RuntimeError("output_root contains unowned uncommitted data")
            destination.rmdir()
        _initialize_trial_root(destination, fixture, settings, encoded_identity)

    config = {
        **identity,
        "run_id": run_id,
        "task_id": task_id,
        "workspace": str(workspace),
        "state_dir": str(state_dir),
    }
    config_path = destination / "worker-config.json"
    result_path = destination / "worker-result.json"
    terminal_result_path = destination / "terminal-result.json"
    if terminal_result_path.is_file():
        cached = TrialResult.model_validate(
            _read_bounded(terminal_result_path, settings.max_output_bytes)
        )
        _validate_result_identity(cached, case.case_id, run_id)
        return cached
    ledger = state_dir / "tasks" / task_id / "runs" / run_id / "ledger.jsonl"
    execution_state_path = destination / "execution-state.json"
    execution_state = _execution_state(execution_state_path, settings.timeout_seconds)
    remaining = execution_state["deadline"] - time.time()
    if remaining <= 0:
        if ledger.is_file():
            result = TrialResult(
                case_id=case.case_id,
                execution="complete",
                outcome="timeout",
                run_id=run_id,
                error="trial wall deadline exhausted before resume",
                elapsed_seconds=max(0.0, time.time() - execution_state["started_at"]),
            )
            _atomic_write(
                terminal_result_path, _json_bytes(result.model_dump(mode="json"))
            )
            return result
        execution_state_path.unlink(missing_ok=True)
        execution_state = _execution_state(
            execution_state_path, settings.timeout_seconds
        )
        remaining = execution_state["deadline"] - time.time()
    _atomic_write(config_path, _json_bytes(config))
    result_path.unlink(missing_ok=True)
    env = dict(os.environ)
    existing_path = env.get("PYTHONPATH")
    runtime_root = Path(__file__).resolve().parents[1]
    python_paths = [str(root)]
    if runtime_root != root:
        python_paths.append(str(runtime_root))
    if existing_path:
        python_paths.append(existing_path)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    runner = process_runner or run_bounded_process
    try:
        process = runner(
            [
                sys.executable,
                "-m",
                "botpipe_optimizer.trial_worker",
                str(config_path),
                str(result_path),
            ],
            cwd=workspace,
            timeout_seconds=max(0.001, remaining),
            max_stream_bytes=max(1024, settings.max_output_bytes // 4),
            env=env,
        )
    except Exception as exc:  # noqa: BLE001 - injected runner/process boundary
        if not ledger.is_file():
            execution_state_path.unlink(missing_ok=True)
        return TrialResult(
            case_id=case.case_id,
            execution="infrastructure_error",
            outcome="process_launch_failed",
            run_id=run_id,
            error=f"{type(exc).__name__}: {exc}",
        )
    log_omissions = []
    if process.stdout_truncated:
        log_omissions.append("worker stdout was truncated")
    if process.stderr_truncated:
        log_omissions.append("worker stderr was truncated")
    changed = _changed_input(root, identity["code_tree_sha256"], "code_root")
    if fixture is not None:
        changed = changed or _changed_input(
            fixture, identity["fixture_tree_sha256"], "fixture_root"
        )
    if changed is not None:
        return TrialResult(
            case_id=case.case_id,
            execution="infrastructure_error",
            outcome="frozen_input_modified",
            run_id=run_id,
            error=changed,
            elapsed_seconds=process.elapsed_seconds,
            omissions=log_omissions,
        )
    if process.timed_out or process.cancelled:
        from .trial_worker import _fit, capture_workspace_outputs

        dispatched = ledger.is_file()
        execution = (
            "complete"
            if process.timed_out and dispatched
            else "interrupted"
            if process.cancelled
            else "infrastructure_error"
        )
        outcome = (
            "timeout"
            if process.timed_out and dispatched
            else "cancelled"
            if process.cancelled
            else "bootstrap_timeout"
        )
        artifacts, output_omissions, _remaining = capture_workspace_outputs(
            case, workspace, fixture, settings.max_output_bytes
        )
        result = _fit(
            TrialResult(
                case_id=case.case_id,
                execution=execution,
                outcome=outcome,
                run_id=run_id,
                error=_process_diagnostic(process, settings.max_output_bytes // 2),
                artifacts=artifacts,
                elapsed_seconds=max(0.0, time.time() - execution_state["started_at"]),
                omissions=[*log_omissions, *output_omissions],
            ),
            settings.max_output_bytes,
        )
        if execution == "complete":
            _atomic_write(
                terminal_result_path,
                _json_bytes(result.model_dump(mode="json")),
            )
        elif not dispatched:
            execution_state_path.unlink(missing_ok=True)
        return result
    if not result_path.is_file():
        dispatched = ledger.is_file()
        if not dispatched:
            execution_state_path.unlink(missing_ok=True)
        return TrialResult(
            case_id=case.case_id,
            execution="interrupted" if dispatched else "infrastructure_error",
            outcome="worker_crashed" if dispatched else "worker_failed",
            run_id=run_id,
            error=_process_diagnostic(process, settings.max_output_bytes // 2),
            elapsed_seconds=process.elapsed_seconds,
            omissions=log_omissions,
        )
    try:
        payload = _read_bounded(result_path, settings.max_output_bytes)
        result = TrialResult.model_validate(payload)
        _validate_result_identity(result, case.case_id, run_id)
    except (OSError, TypeError, ValueError) as exc:
        if not ledger.is_file():
            execution_state_path.unlink(missing_ok=True)
        return TrialResult(
            case_id=case.case_id,
            execution="infrastructure_error",
            outcome="invalid_worker_result",
            run_id=run_id,
            error=(
                f"{type(exc).__name__}: {exc}; "
                f"{_process_diagnostic(process, settings.max_output_bytes // 2)}"
            ),
            elapsed_seconds=process.elapsed_seconds,
            omissions=log_omissions,
        )
    if process.exit_code != 0 and result.execution != "infrastructure_error":
        return result.model_copy(
            update={
                "execution": "infrastructure_error",
                "outcome": "worker_failed",
                "error": result.error
                or _process_diagnostic(process, settings.max_output_bytes // 2),
                "omissions": [*result.omissions, *log_omissions],
            }
        )
    if log_omissions:
        result = result.model_copy(
            update={"omissions": [*result.omissions, *log_omissions]}
        )
    result = result.model_copy(
        update={
            "elapsed_seconds": max(0.0, time.time() - execution_state["started_at"])
        }
    )
    if result.execution == "complete":
        _atomic_write(terminal_result_path, _json_bytes(result.model_dump(mode="json")))
    return result


def _initialize_workspace(
    destination: Path,
    fixture: Path | None,
    settings: TrialSettings,
) -> None:
    parent = destination.parent
    temporary = Path(tempfile.mkdtemp(prefix=".trial-workspace-", dir=parent))
    try:
        if fixture is not None:
            _copy_tree_contents(fixture, temporary, settings)
        _make_owner_writable(temporary)
        _check_tree(temporary, settings)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _initialize_trial_root(
    destination: Path,
    fixture: Path | None,
    settings: TrialSettings,
    encoded_identity: bytes,
) -> None:
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.init-", dir=destination.parent)
    )
    try:
        _initialize_workspace(temporary / "workspace", fixture, settings)
        (temporary / "state").mkdir()
        _atomic_write(temporary / "trial.json", encoded_identity)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _copy_tree_contents(
    source: Path, destination: Path, settings: TrialSettings
) -> None:
    _check_tree(source, settings)
    for child in source.iterdir():
        if child.is_symlink():
            raise ValueError(f"fixture contains a symlink: {child.relative_to(source)}")
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, symlinks=False)
        elif child.is_file():
            shutil.copy2(child, target)
        else:
            raise ValueError(f"fixture contains a non-regular entry: {child}")


def _check_tree(root: Path, settings: TrialSettings) -> None:
    files = size = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"fixture contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            files += 1
            size += path.stat().st_size
            if files > settings.max_fixture_files:
                raise ValueError("fixture exceeds max_fixture_files")
            if size > settings.max_fixture_bytes:
                raise ValueError("fixture exceeds max_fixture_bytes")


def _make_owner_writable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise ValueError(f"fixture contains a symlink: {path.relative_to(root)}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            path.chmod(mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        elif path.is_file():
            path.chmod(mode | stat.S_IWUSR)


def _process_diagnostic(process: Any, limit: int) -> str:
    parts = [f"exit_code={process.exit_code}"]
    if process.stderr:
        parts.append(f"stderr={process.stderr}")
    elif process.stdout:
        parts.append(f"stdout={process.stdout}")
    value = "; ".join(parts)
    return value if len(value) <= limit else value[-limit:]


def _validate_result_identity(
    result: TrialResult, expected_case_id: str, expected_run_id: str
) -> None:
    if result.case_id != expected_case_id or result.run_id != expected_run_id:
        raise ValueError("trial result identity does not match its durable trial")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative_path = path.relative_to(root)
        if _transient_path(relative_path):
            continue
        relative = relative_path.as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.readlink(path).encode("utf-8"))
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise ValueError(f"tree contains a non-regular entry: {path}")
    return digest.hexdigest()


def _transient_path(path: Path) -> bool:
    ignored = {".git", ".venv", ".pytest_cache", ".ruff_cache", "__pycache__", "build"}
    return (
        bool(set(path.parts) & ignored)
        or any(part.endswith(".egg-info") for part in path.parts)
        or path.suffix in {".pyc", ".pyo"}
    )


def _changed_input(root: Path, expected: Any, label: str) -> str | None:
    try:
        current = _tree_digest(root)
    except (OSError, ValueError) as exc:
        return f"could not verify frozen {label}: {type(exc).__name__}: {exc}"
    return None if current == expected else f"frozen {label} changed during trial"


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _execution_state(path: Path, timeout_seconds: float) -> dict[str, float]:
    if path.is_file():
        value = _read_bounded(path, 4096)
        if (
            not isinstance(value, dict)
            or type(value.get("started_at")) not in {int, float}
            or type(value.get("deadline")) not in {int, float}
        ):
            raise ValueError("execution-state.json is invalid")
        return {
            "started_at": float(value["started_at"]),
            "deadline": float(value["deadline"]),
        }
    started = time.time()
    value = {"started_at": started, "deadline": started + timeout_seconds}
    _atomic_write(path, _json_bytes(value))
    return value


def _read_bounded(path: Path, limit: int) -> Any:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds max_output_bytes")
    return json.loads(data)


__all__ = ["run_trial"]
