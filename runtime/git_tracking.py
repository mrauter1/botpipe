"""Runtime-owned git tracking for run observability."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.schema_registry import GIT_TRACKING_SCHEMA as CANONICAL_GIT_TRACKING_SCHEMA
from extensions.git.repo import GitRepo
from .config import GitTrackingRuntimeConfig
from .workspace import append_run_git_step, update_run_git_tracking


GIT_TRACKING_SCHEMA = CANONICAL_GIT_TRACKING_SCHEMA
GIT_TRACKING_FILENAME = "git_tracking.jsonl"


class RuntimeGitTrackingError(RuntimeError):
    """Raised when runtime-owned git tracking cannot proceed."""


class RuntimeGitTracker:
    def __init__(
        self,
        *,
        root: Path,
        run_dir: Path | None,
        workflow_name: str,
        task_id: str,
        run_id: str,
        config: GitTrackingRuntimeConfig,
    ) -> None:
        self._root = root.resolve()
        self._run_dir = None if run_dir is None else run_dir.resolve()
        self._workflow_name = workflow_name
        self._task_id = task_id
        self._run_id = run_id
        self._config = config
        self._repo: GitRepo | None = None
        self._prepared_payload: dict[str, Any] = self._disabled_payload()

    def prepare_before_workspace_creation(self) -> dict[str, object]:
        if not self._runtime_enabled:
            self._prepared_payload = self._disabled_payload()
            return dict(self._prepared_payload)

        repo = GitRepo.discover(self._root)
        if repo is None:
            return self._handle_prepare_error("git tracking disabled because no git repository was found")
        if repo.is_dirty():
            return self._handle_prepare_error("git tracking disabled because repository was dirty at run start")

        self._repo = repo
        self._prepared_payload = {
            "enabled": True,
            "eligible": True,
            "commit_policy": self._config.commit_policy,
            "repo_root": str(repo.root),
            "commit_before_run": repo.head(),
            "git_tracking_file": GIT_TRACKING_FILENAME,
        }
        return dict(self._prepared_payload)

    def bind_run_dir(self, run_dir: Path) -> None:
        self._run_dir = run_dir.resolve()
        self._operate(self._bind_run_dir_operation)

    def commit_run_initialized(self) -> dict[str, object]:
        if not self._active:
            return dict(self._prepared_payload)
        result = self._operate(self._commit_run_initialized_operation)
        if result is None:
            return dict(self._prepared_payload)
        return result

    def before_step(self, *, sequence: int, step_name: str) -> dict[str, object]:
        if not self._active:
            return dict(self._prepared_payload)
        result = self._operate(
            lambda: {
                "enabled": True,
                "eligible": True,
                "sequence": sequence,
                "step_name": step_name,
                "commit_before_step": self._repo.head(),
            }
        )
        if result is None:
            return dict(self._prepared_payload)
        return result

    def after_step(self, *, sequence: int, step_name: str, commit_before_step: str | None) -> dict[str, object]:
        if not self._active:
            return dict(self._prepared_payload)
        result = self._operate(
            lambda: self._after_step_operation(
                sequence=sequence,
                step_name=step_name,
                commit_before_step=commit_before_step,
            )
        )
        if result is None:
            return dict(self._prepared_payload)
        return result

    def after_run(self, *, terminal: str | None) -> dict[str, object]:
        if not self._active:
            return dict(self._prepared_payload)
        result = self._operate(lambda: self._after_run_operation(terminal=terminal))
        if result is None:
            return dict(self._prepared_payload)
        return result

    def on_fatal(self, *, step_name: str | None, error: BaseException) -> dict[str, object]:
        if not self._active:
            return dict(self._prepared_payload)
        result = self._operate(lambda: self._fatal_operation(step_name=step_name, error=error))
        if result is None:
            return dict(self._prepared_payload)
        return result

    @property
    def _runtime_enabled(self) -> bool:
        return self._config.enabled and self._config.commit_policy != "off"

    @property
    def _active(self) -> bool:
        return self._runtime_enabled and self._repo is not None

    @property
    def _git_tracking_file(self) -> Path:
        return self._require_run_dir() / GIT_TRACKING_FILENAME

    def _require_run_dir(self) -> Path:
        if self._run_dir is None:
            raise RuntimeGitTrackingError("runtime git tracker is not bound to a run directory")
        return self._run_dir

    def _handle_prepare_error(self, message: str) -> dict[str, object]:
        if self._config.failure_mode == "ignore":
            self._repo = None
            self._prepared_payload = self._disabled_payload(error=message)
            return dict(self._prepared_payload)
        raise RuntimeGitTrackingError(message)

    def _disabled_payload(self, *, error: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": False,
            "eligible": False,
            "commit_policy": self._config.commit_policy,
        }
        if error is not None:
            payload["error"] = error
        return payload

    def _bind_run_dir_operation(self) -> None:
        if self._active:
            self._git_tracking_file.parent.mkdir(parents=True, exist_ok=True)
            self._git_tracking_file.touch(exist_ok=True)
        update_run_git_tracking(self._require_run_dir(), self._prepared_payload)

    def _commit_run_initialized_operation(self) -> dict[str, object]:
        commit_after_init, created_commit = self._repo.commit_all(self._init_commit_message())
        payload = self._record(
            event_type="run_initialized",
            commit_before_run=self._prepared_payload.get("commit_before_run"),
            commit_after_init=commit_after_init,
            created_commit=created_commit,
        )
        update_run_git_tracking(
            self._require_run_dir(),
            {
                "enabled": True,
                "eligible": True,
                "commit_after_init": commit_after_init,
            },
        )
        return payload

    def _after_step_operation(
        self,
        *,
        sequence: int,
        step_name: str,
        commit_before_step: str | None,
    ) -> dict[str, object]:
        if commit_before_step is None:
            commit_before_step = self._repo.head()
        if self._config.commit_policy == "step":
            commit_after_step, created_commit = self._repo.commit_all(
                self._step_commit_message(sequence=sequence, step_name=step_name)
            )
            event_type = "step_committed"
        else:
            commit_after_step = commit_before_step
            created_commit = False
            event_type = "step_observed"
        payload = self._record(
            event_type=event_type,
            sequence=sequence,
            step_name=step_name,
            commit_before_step=commit_before_step,
            commit_after_step=commit_after_step,
            created_commit=created_commit,
        )
        append_run_git_step(
            self._require_run_dir(),
            {
                "sequence": sequence,
                "step_name": step_name,
                "commit_before_step": commit_before_step,
                "commit_after_step": commit_after_step,
                "created_commit": created_commit,
            },
        )
        return payload

    def _after_run_operation(self, *, terminal: str | None) -> dict[str, object]:
        commit_after_run, created_commit = self._repo.commit_all(self._finish_commit_message(terminal=terminal))
        payload = self._record(
            event_type="run_finished",
            terminal=terminal,
            commit_after_run=commit_after_run,
            created_commit=created_commit,
        )
        update_run_git_tracking(self._require_run_dir(), {"commit_after_run": commit_after_run})
        self._flush_runtime_metadata()
        return payload

    def _fatal_operation(self, *, step_name: str | None, error: BaseException) -> dict[str, object]:
        commit_after_run, created_commit = self._repo.commit_all(self._fatal_commit_message())
        payload = self._record(
            event_type="fatal_committed",
            step_name=step_name,
            error_type=type(error).__name__,
            error_message=str(error),
            commit_after_run=commit_after_run,
            created_commit=created_commit,
        )
        update_run_git_tracking(self._require_run_dir(), {"commit_after_run": commit_after_run})
        self._flush_runtime_metadata()
        return payload

    def _operate(self, operation):
        try:
            return operation()
        except Exception as exc:
            return self._handle_runtime_error(exc)

    def _handle_runtime_error(self, exc: Exception):
        if self._config.failure_mode == "ignore":
            message = f"git tracking disabled after runtime error: {exc}"
            self._repo = None
            self._prepared_payload = self._disabled_payload(error=message)
            if self._run_dir is not None:
                try:
                    update_run_git_tracking(self._run_dir, self._prepared_payload)
                except Exception:
                    return None
            return None
        if isinstance(exc, RuntimeGitTrackingError):
            raise exc
        raise RuntimeGitTrackingError(str(exc)) from exc

    def _record(self, *, event_type: str, **fields: object) -> dict[str, object]:
        payload = {
            "schema": GIT_TRACKING_SCHEMA,
            "event_type": event_type,
            "workflow": self._workflow_name,
            "task_id": self._task_id,
            "run_id": self._run_id,
            "timestamp": _utcnow(),
            **fields,
        }
        run_dir = self._require_run_dir()
        self._git_tracking_file.parent.mkdir(parents=True, exist_ok=True)
        with self._git_tracking_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def _init_commit_message(self) -> str:
        return f"autoloop: init {self._workflow_name} {self._run_id}"

    def _step_commit_message(self, *, sequence: int, step_name: str) -> str:
        return f"autoloop: step {self._workflow_name} {self._run_id} {sequence} {step_name}"

    def _finish_commit_message(self, *, terminal: str | None) -> str:
        return f"autoloop: finish {self._workflow_name} {self._run_id} {terminal or 'unknown'}"

    def _fatal_commit_message(self) -> str:
        return f"autoloop: fatal {self._workflow_name} {self._run_id}"

    def _flush_runtime_metadata(self) -> None:
        self._repo.commit_all(self._metadata_commit_message())

    def _metadata_commit_message(self) -> str:
        return f"autoloop: metadata {self._workflow_name} {self._run_id}"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "GIT_TRACKING_FILENAME",
    "GIT_TRACKING_SCHEMA",
    "RuntimeGitTracker",
    "RuntimeGitTrackingError",
]
