"""Readable, append-only execution history for durable workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .storage import sync_directory

FORMAT_VERSION = 1
_INLINE_LIMIT = 8 * 1024
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def now():
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class JournalSnapshot:
    run: dict[str, Any]
    operations: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    last_seq: int = 0


@dataclass
class _RunState:
    run: dict[str, Any]
    operations: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    attempts: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    budgets: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_seq: int = 0
    prefix_bytes: int = 0
    file_bytes: int = 0
    incomplete_tail: bool = False
    poisoned: BaseException | None = None


class Journal:
    """A state-root journal with one authoritative JSONL ledger per run."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self._index_lock = threading.RLock()
        self._locks: dict[str, threading.RLock] = {}
        self._states: dict[str, _RunState] = {}
        self._operation_runs: dict[str, str] = {}

    def close(self):
        """The file-native journal holds no persistent handles."""

    @staticmethod
    def _safe(value: str, name: str) -> str:
        if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
            raise ValueError(f"{name} must be a safe identifier")
        return value

    @staticmethod
    def _timestamp(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return False
        return (
            parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
        )

    def _lock(self, run_id: str) -> threading.RLock:
        with self._index_lock:
            return self._locks.setdefault(run_id, threading.RLock())

    def _run_paths(self, run_id: str) -> list[Path]:
        self._safe(run_id, "run_id")
        tasks = self.path / "tasks"
        if not tasks.is_dir():
            return []
        paths = sorted(tasks.glob(f"*/runs/{run_id}/ledger.jsonl"))
        for candidate in paths:
            try:
                candidate.resolve(strict=True).relative_to(self.path)
            except ValueError as error:
                raise ValueError(
                    f"Run ledger escapes the state root: {candidate}"
                ) from error
        return paths

    def _ledger_path(self, run_id: str) -> Path:
        paths = self._run_paths(run_id)
        if not paths:
            raise KeyError(f"Unknown run {run_id}")
        if len(paths) != 1:
            raise ValueError(f"Ambiguous run {run_id}: found {len(paths)} ledgers")
        return paths[0]

    @staticmethod
    def _encode(value: Any) -> bytes:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )

    @staticmethod
    def _write_all(descriptor: int, content: bytes) -> None:
        view = memoryview(content)
        written = 0
        while written < len(content):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("ledger write made no progress")
            written += count

    @staticmethod
    def _sync_file(path: Path) -> None:
        # Windows FlushFileBuffers requires a handle with write access.
        descriptor = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _publish_immutable(cls, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.is_symlink():
                raise ValueError(f"Immutable journal payload is a symlink: {path}")
            if path.read_bytes() != content:
                raise ValueError(f"Immutable journal payload differs: {path}")
            # Existing equal bytes may be from an earlier process whose sync
            # acknowledgement was lost. Re-establish durability before the
            # authoritative ledger is allowed to reference them.
            cls._sync_file(path)
            sync_directory(path.parent)
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            cls._write_all(descriptor, content)
            os.fsync(descriptor)
        except BaseException:
            try:
                os.close(descriptor)
            finally:
                temporary.unlink(missing_ok=True)
            raise
        else:
            os.close(descriptor)
        try:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes() != content:
                    raise ValueError(f"Immutable journal payload differs: {path}")
                cls._sync_file(path)
            sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _publish_owned(cls, run_dir: Path, path: Path, content: bytes) -> None:
        resolved_run = run_dir.resolve(strict=True)
        try:
            path.parent.resolve().relative_to(resolved_run)
        except ValueError as error:
            raise ValueError(
                f"Journal payload path escapes its run directory: {path}"
            ) from error
        missing = []
        parent = path.parent
        while not parent.exists():
            missing.append(parent)
            parent = parent.parent
        try:
            parent.resolve(strict=True).relative_to(resolved_run)
        except ValueError as error:
            raise ValueError(
                f"Journal payload path escapes its run directory: {path}"
            ) from error
        for directory in reversed(missing):
            directory.mkdir()
            sync_directory(directory.parent)
        cls._publish_immutable(path, content)

    @staticmethod
    def _reference(run_dir: Path, path: Path, content: bytes) -> dict[str, Any]:
        return {
            "path": path.relative_to(run_dir).as_posix(),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    @staticmethod
    def _operation_component(operation_id: str) -> str:
        if isinstance(operation_id, str) and _SAFE_ID.fullmatch(operation_id):
            return operation_id
        encoded = str(operation_id).encode("utf-8")
        return "operation-" + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _read_reference(cls, run_dir: Path, reference: dict[str, Any]) -> bytes:
        relative = reference.get("path")
        if not isinstance(relative, str):
            raise ValueError("Journal payload reference has no path")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Unsafe run-owned payload path {relative!r}")
        path = run_dir / candidate
        try:
            resolved_run = run_dir.resolve(strict=True)
            resolved = path.resolve(strict=True)
            resolved.relative_to(resolved_run)
            content = resolved.read_bytes()
        except ValueError as error:
            raise ValueError(
                f"Journal payload escapes its run directory: {path}"
            ) from error
        except OSError as error:
            raise ValueError(f"Missing journal payload {path}") from error
        if len(content) != reference.get("size"):
            raise ValueError(f"Journal payload size mismatch: {path}")
        if hashlib.sha256(content).hexdigest() != reference.get("sha256"):
            raise ValueError(f"Journal payload digest mismatch: {path}")
        return content

    def _payload(self, run_dir: Path, operation_id: str, label: str, value: Any):
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        marker_shaped = isinstance(value, dict) and set(value) in (
            {"$ledger_payload"},
            {"$ledger_text"},
        )
        if len(encoded) <= _INLINE_LIMIT and not marker_shaped:
            return value
        digest = hashlib.sha256(encoded).hexdigest()
        safe_label = (
            label if isinstance(label, str) and _SAFE_ID.fullmatch(label) else "value"
        )
        path = (
            run_dir
            / "operations"
            / self._operation_component(operation_id)
            / "payloads"
            / f"{safe_label}-{digest[:16]}.json"
        )
        self._publish_owned(run_dir, path, encoded)
        return {"$ledger_payload": self._reference(run_dir, path, encoded)}

    def _run_payload(self, run_dir: Path, label: str, value: Any):
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        marker_shaped = isinstance(value, dict) and set(value) in (
            {"$ledger_payload"},
            {"$ledger_text"},
        )
        if len(encoded) <= _INLINE_LIMIT and not marker_shaped:
            return value
        digest = hashlib.sha256(encoded).hexdigest()
        path = run_dir / "payloads" / f"{label}-{digest[:16]}.json"
        self._publish_owned(run_dir, path, encoded)
        return {"$ledger_payload": self._reference(run_dir, path, encoded)}

    @classmethod
    def _resolve_payload(cls, run_dir: Path, value: Any):
        if (
            isinstance(value, dict)
            and set(value) == {"$ledger_payload"}
            and isinstance(value["$ledger_payload"], dict)
        ):
            content = cls._read_reference(run_dir, value["$ledger_payload"])
            try:
                return json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Malformed JSON journal payload") from error
        if (
            isinstance(value, dict)
            and set(value) == {"$ledger_text"}
            and isinstance(value["$ledger_text"], dict)
        ):
            content = cls._read_reference(run_dir, value["$ledger_text"])
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("Malformed UTF-8 journal text payload") from error
        return value

    @classmethod
    def _resolve_response(cls, run_dir: Path, value: Any):
        response = cls._resolve_payload(run_dir, value)
        if not isinstance(response, dict):
            return response
        text = response.get("text")
        if (
            isinstance(text, dict)
            and set(text) == {"$ledger_text"}
            and isinstance(text["$ledger_text"], dict)
        ):
            response = dict(response)
            response["text"] = cls._resolve_payload(run_dir, text)
        return response

    @classmethod
    def _validate_attempt_status(
        cls,
        operation_id: str,
        attempt: int,
        current: dict[str, Any],
        update: dict[str, Any],
    ) -> None:
        attempt_status = update.get("status")
        if attempt_status is None:
            return
        allowed_statuses = {
            "configured",
            "thread_bound",
            "turn_intent",
            "turn_acknowledged",
            "turn_terminal",
            "response_received",
            "stopped",
            "completed",
            "failed",
        }
        if attempt_status not in allowed_statuses:
            raise ValueError(f"invalid attempt status {attempt_status!r}")
        current_status = current.get("status")
        if (
            current_status in {"completed", "failed", "stopped"}
            and attempt_status != current_status
        ):
            raise ValueError(
                f"terminal attempt {operation_id}/{attempt} cannot change "
                f"from {current_status!r} to {attempt_status!r}"
            )

    @classmethod
    def _apply(
        cls, state: _RunState | None, record: dict[str, Any], run_dir: Path
    ) -> _RunState:
        seq, event, run_id, data = (
            record.get("seq"),
            record.get("event"),
            record.get("run_id"),
            record.get("data"),
        )
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
            raise ValueError("record sequence must be a positive integer")
        if not isinstance(event, str) or not isinstance(data, dict):
            raise ValueError("record event and data are invalid")
        if not cls._timestamp(record.get("at")):
            raise ValueError("record timestamp is not UTC ISO-8601")
        if state is None:
            if seq != 1 or event != "run_created":
                raise ValueError("ledger must begin with run_created at sequence 1")
            if data.get("format_version") != FORMAT_VERSION:
                raise ValueError(
                    f"Unsupported ledger format {data.get('format_version')!r}"
                )
            metadata, reference = data.get("run"), data.get("input")
            if not isinstance(metadata, dict) or metadata.get("run_id") != run_id:
                raise ValueError("run metadata does not match its ledger identity")
            task_id = run_dir.parent.parent.name
            if run_dir.name != run_id or metadata.get("task_id") != task_id:
                raise ValueError("run metadata does not match its task/run path")
            if not isinstance(reference, dict):
                raise ValueError("run_created has no input reference")
            try:
                inputs = json.loads(cls._read_reference(run_dir, reference))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Malformed input.json") from error
            if not isinstance(inputs, dict) or set(inputs) != {"args", "kwargs"}:
                raise ValueError("input.json must contain args and kwargs")
            request_reference = data.get("request")
            if request_reference is not None:
                if not isinstance(request_reference, dict):
                    raise ValueError("run_created request reference is invalid")
                try:
                    cls._read_reference(run_dir, request_reference).decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError("Malformed request.md") from error
            state = _RunState(run={**metadata, **inputs})
        elif seq != state.last_seq + 1:
            raise ValueError(
                f"sequence gap: expected {state.last_seq + 1}, found {seq}"
            )
        elif run_id != state.run.get("run_id"):
            raise ValueError("record run identity changed")

        operation_id = record.get("operation_id")
        if event == "run_updated":
            if (
                state.run.get("status") == "completed"
                and data.get("status", "completed") != "completed"
            ):
                raise ValueError("completed run status cannot be changed")
            state.run.update(
                {
                    key: cls._resolve_payload(run_dir, value)
                    for key, value in data.items()
                }
            )
        elif event == "operation_started":
            operation = data.get("operation")
            if not isinstance(operation, dict) or operation.get("id") != operation_id:
                raise ValueError("operation_started has invalid operation facts")
            if operation_id in state.operations:
                raise ValueError(f"duplicate operation {operation_id}")
            identity = (operation.get("scope"), operation.get("ordinal"))
            if any(
                (op.get("scope"), op.get("ordinal")) == identity
                for op in state.operations.values()
            ):
                raise ValueError(f"duplicate operation position {identity!r}")
            operation = dict(operation)
            operation["inputs"] = cls._resolve_payload(run_dir, operation.get("inputs"))
            operation["started_seq"] = seq
            state.operations[operation_id] = operation
        elif event in {
            "operation_completed",
            "operation_failed",
            "operation_response",
            "human_input_requested",
        }:
            operation = state.operations.get(operation_id)
            if operation is None:
                raise ValueError(f"record references unknown operation {operation_id}")
            target = {
                "operation_completed": "completed",
                "operation_failed": "failed",
                "operation_response": "response",
                "human_input_requested": "waiting",
            }[event]
            allowed = {
                "operation_completed": {"started", "response"},
                "operation_failed": {"started", "response"},
                "operation_response": {"started", "waiting", "response"},
                "human_input_requested": {"started", "waiting"},
            }[event]
            projection = {
                key: cls._resolve_response(run_dir, value)
                if key == "response"
                else cls._resolve_payload(run_dir, value)
                for key, value in data.items()
            }
            comparable = {
                key: value for key, value in projection.items() if key != "session_key"
            }
            if operation.get("status") == target and all(
                operation.get(k) == v for k, v in comparable.items()
            ):
                pass
            elif operation.get("status") not in allowed:
                raise ValueError(
                    f"operation {operation_id} cannot change from {operation.get('status')!r} to {target!r}"
                )
            else:
                operation.update(comparable)
                operation["status"] = target
                if target in {"completed", "failed"}:
                    operation["finished_at"] = record["at"]
                if event == "operation_response" and isinstance(
                    operation.get("response"), dict
                ):
                    response = operation["response"]
                    metadata = (
                        response.get("metadata")
                        if isinstance(response.get("metadata"), dict)
                        else {}
                    )
                    for key, value in {
                        "thread_id": response.get("session_id"),
                        "turn_id": metadata.get("turn_id"),
                        "probe_hash": metadata.get("probe_hash"),
                        "enforcement": metadata.get("enforcement"),
                    }.items():
                        if value is not None:
                            operation[key] = value
        elif event == "provider_metadata":
            operation = state.operations.get(operation_id)
            if operation is None or operation.get("kind") != "provider":
                raise ValueError(
                    f"provider metadata references invalid operation {operation_id}"
                )
            operation.update(data)
        elif event == "attempt_prepared":
            attempt = data.get("attempt")
            if (
                operation_id not in state.operations
                or not isinstance(attempt, int)
                or attempt < 1
            ):
                raise ValueError("attempt_prepared has invalid identity")
            key = (operation_id, attempt)
            existing = state.attempts.get(key)
            if existing is not None and existing != data:
                raise ValueError(
                    f"attempt {operation_id}/{attempt} was prepared differently"
                )
            prompt_reference = data.get("prompt")
            request_reference = data.get("request")
            if not isinstance(prompt_reference, dict) or not isinstance(
                request_reference, dict
            ):
                raise ValueError("attempt_prepared has invalid file references")
            try:
                cls._read_reference(run_dir, prompt_reference).decode("utf-8")
                request_value = json.loads(
                    cls._read_reference(run_dir, request_reference)
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("attempt files are not valid UTF-8/JSON") from error
            if not isinstance(request_value, dict):
                raise ValueError("attempt request file is not a JSON object")
            state.attempts[key] = dict(data)
        elif event == "attempt_checkpoint":
            attempt, update = data.get("attempt"), data.get("update")
            key = (operation_id, attempt)
            if key not in state.attempts or not isinstance(update, dict):
                raise ValueError("attempt checkpoint has no prepared attempt")
            resolved = {
                name: cls._resolve_response(run_dir, value)
                if name == "response"
                else cls._resolve_payload(run_dir, value)
                for name, value in update.items()
            }
            cls._validate_attempt_status(
                operation_id, attempt, state.attempts[key], resolved
            )
            state.attempts[key].update(resolved)
            operation = state.operations[operation_id]
            for name in ("thread_id", "turn_id", "preset", "enforcement", "probe_hash"):
                if name in resolved:
                    operation[name] = resolved[name]
            if "session_id" in resolved:
                operation["thread_id"] = resolved["session_id"]
            response = resolved.get("response")
            if isinstance(response, dict):
                if response.get("session_id") is not None:
                    operation["thread_id"] = response["session_id"]
                metadata = response.get("metadata")
                if isinstance(metadata, dict):
                    for name in ("turn_id", "probe_hash", "enforcement"):
                        if metadata.get(name) is not None:
                            operation[name] = metadata[name]
        elif event == "budget_created":
            budget_id, budget = data.get("budget_id"), data.get("state")
            if not isinstance(budget_id, str) or not isinstance(budget, dict):
                raise ValueError("budget_created is malformed")
            if budget_id in state.budgets and state.budgets[budget_id] != budget:
                raise ValueError(f"budget {budget_id} changed configuration")
            state.budgets[budget_id] = dict(budget)
        elif event in {"provider_budgets_observed", "provider_dispatch_reserved"}:
            states = data.get("budget_states", {})
            if not isinstance(states, dict):
                raise ValueError(f"{event} has invalid budget states")
            for budget_id, budget in states.items():
                if budget_id not in state.budgets or not isinstance(budget, dict):
                    raise ValueError(f"{event} references unknown budget {budget_id}")
                state.budgets[budget_id] = dict(budget)
            if event == "provider_dispatch_reserved" and operation_id is not None:
                attempt = data.get("attempt")
                attempt_state = state.attempts.get((operation_id, attempt))
                if attempt_state is None:
                    raise ValueError("dispatch reservation has no prepared attempt")
                attempt_state["dispatch_authorized"] = True
                if "dispatch_id" in data:
                    attempt_state["dispatch_id"] = data["dispatch_id"]

        state.last_seq = seq
        state.events.append(record)
        return state

    @classmethod
    def _read_path(cls, ledger: Path) -> _RunState:
        boundary, state, position, last_line = ledger.stat().st_size, None, 0, b""
        with ledger.open("rb") as stream:
            while position < boundary:
                line = stream.readline(boundary - position)
                last_line = line
                position += len(line)
                if not line.endswith(b"\n"):
                    if state is None:
                        raise ValueError(f"Empty ledger {ledger}")
                    state.incomplete_tail = True
                    break
                try:
                    record = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError(
                        f"Corrupt ledger {ledger} at byte {position - len(line)}"
                    ) from error
                if not isinstance(record, dict):
                    raise ValueError(
                        f"Corrupt ledger {ledger}: record is not an object"
                    )
                try:
                    state = cls._apply(state, record, ledger.parent)
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"Corrupt ledger {ledger} at sequence {record.get('seq', '?')}: {error}"
                    ) from error
        if state is None:
            raise ValueError(f"Empty ledger {ledger}")
        state.prefix_bytes = (
            position - len(last_line) if state.incomplete_tail else position
        )
        state.file_bytes = boundary
        return state

    def _load(self, run_id: str, *, fresh: bool = False) -> _RunState:
        with self._index_lock:
            if not fresh and run_id in self._states:
                cached = self._states[run_id]
            else:
                cached = None
        ledger = self._ledger_path(run_id)
        if cached is not None:
            if (
                cached.poisoned is not None
                or ledger.stat().st_size == cached.file_bytes
            ):
                return cached
        state = self._read_path(ledger)
        with self._index_lock:
            if not fresh:
                self._states[run_id] = state
                for operation_id in state.operations:
                    previous = self._operation_runs.setdefault(operation_id, run_id)
                    if previous != run_id:
                        raise ValueError(f"Ambiguous operation {operation_id}")
        return state

    def _repair_tail(self, run_id: str, state: _RunState, ledger: Path) -> None:
        if not state.incomplete_tail:
            return
        with ledger.open("r+b") as stream:
            stream.truncate(state.prefix_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        state.incomplete_tail = False
        state.file_bytes = state.prefix_bytes
        self._append_locked(
            run_id, "ledger_tail_repaired", {"truncated_to": state.prefix_bytes}
        )

    def _append_locked(
        self,
        run_id: str,
        event: str,
        data: dict[str, Any],
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        state = self._load(run_id)
        if state.poisoned is not None:
            raise RuntimeError(
                f"Ledger writer for {run_id} is unusable"
            ) from state.poisoned
        ledger = self._ledger_path(run_id)
        self._repair_tail(run_id, state, ledger)
        record = {
            "seq": state.last_seq + 1,
            "at": now(),
            "event": event,
            "run_id": run_id,
            "data": data,
        }
        if operation_id is not None:
            record["operation_id"] = operation_id
        encoded, offset = self._encode(record), ledger.stat().st_size
        descriptor = os.open(
            ledger, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0)
        )
        try:
            try:
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
            except BaseException as first_error:
                os.close(descriptor)
                descriptor = -1
                try:
                    with ledger.open("rb") as confirmation:
                        confirmation.seek(offset)
                        observed = confirmation.read(len(encoded))
                    if not encoded.startswith(observed):
                        raise OSError(
                            "ledger bytes differ at the retained append offset"
                        )
                    if len(observed) < len(encoded):
                        repair = os.open(
                            ledger, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0)
                        )
                        try:
                            self._write_all(repair, encoded[len(observed) :])
                            os.fsync(repair)
                        finally:
                            os.close(repair)
                    else:
                        self._sync_file(ledger)
                except BaseException as confirmation_error:
                    state.poisoned = confirmation_error
                    raise first_error from confirmation_error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        canonical_record = json.loads(encoded)
        try:
            self._apply(state, canonical_record, ledger.parent)
        except BaseException as error:
            state.poisoned = error
            raise
        state.prefix_bytes = offset + len(encoded)
        state.file_bytes = state.prefix_bytes
        return canonical_record

    def _append(self, run_id, event, data, operation_id=None):
        with self._lock(run_id):
            return self._append_locked(run_id, event, data, operation_id)

    def create_run(self, data):
        data = dict(data)
        run_id, task_id = (
            self._safe(data.get("run_id"), "run_id"),
            self._safe(data.get("task_id"), "task_id"),
        )
        request_text = data.pop("request_text", None)
        if request_text is not None and not isinstance(request_text, str):
            raise TypeError("request_text must be text or None")
        with self._lock(run_id):
            if self._run_paths(run_id):
                raise ValueError(f"Run ID already exists: {run_id}")
            run_dir = self.path / "tasks" / task_id / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            sync_directory(run_dir.parent)
            inputs = {
                "args": data.pop("args", None),
                "kwargs": data.pop("kwargs", None),
            }
            input_content = (
                json.dumps(
                    inputs,
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            )
            input_path = run_dir / "input.json"
            self._publish_owned(run_dir, input_path, input_content)
            record_data = {
                "format_version": FORMAT_VERSION,
                "run": data,
                "input": self._reference(run_dir, input_path, input_content),
            }
            if request_text is not None:
                request_content = request_text.encode("utf-8")
                request_path = run_dir / "request.md"
                self._publish_owned(run_dir, request_path, request_content)
                record_data["request"] = self._reference(
                    run_dir, request_path, request_content
                )
            record = {
                "seq": 1,
                "at": data.get("created_at") or now(),
                "event": "run_created",
                "run_id": run_id,
                "data": record_data,
            }
            ledger = run_dir / "ledger.jsonl"
            encoded_record = self._encode(record)
            self._publish_immutable(ledger, encoded_record)
            state = self._apply(None, json.loads(encoded_record), run_dir)
            state.prefix_bytes = ledger.stat().st_size
            state.file_bytes = state.prefix_bytes
            with self._index_lock:
                self._states[run_id] = state

    def run(self, run_id):
        with self._lock(run_id):
            return deepcopy(self._load(run_id).run)

    def update_run(self, run_id, **updates):
        with self._lock(run_id):
            current = self._load(run_id).run
            if (
                current.get("status") == "completed"
                and updates.get("status", "completed") != "completed"
            ):
                raise RuntimeError("Completed run status cannot be changed")
            changes = {
                key: value
                for key, value in updates.items()
                if current.get(key) != value
            }
            if changes:
                run_dir = self._ledger_path(run_id).parent
                durable = {
                    key: self._run_payload(run_dir, key, value)
                    if key == "value"
                    else value
                    for key, value in changes.items()
                }
                self._append_locked(run_id, "run_updated", durable)

    def runs(self):
        ledgers = (
            sorted((self.path / "tasks").glob("*/runs/*/ledger.jsonl"))
            if (self.path / "tasks").is_dir()
            else []
        )
        runs = [self._read_run_listing(ledger) for ledger in ledgers]
        return sorted(runs, key=lambda item: item.get("created_at", ""), reverse=True)

    @classmethod
    def _read_run_listing(cls, ledger: Path) -> dict[str, Any]:
        metadata = cls._read_run_header(ledger)
        run_id = metadata["run_id"]
        expected = 1
        boundary = ledger.stat().st_size
        with ledger.open("rb") as stream:
            stream.readline()
            while stream.tell() < boundary:
                line = stream.readline(boundary - stream.tell())
                if not line.endswith(b"\n"):
                    break
                try:
                    record = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError(f"Corrupt ledger listing: {ledger}") from error
                expected += 1
                if (
                    not isinstance(record, dict)
                    or record.get("seq") != expected
                    or record.get("run_id") != run_id
                    or not isinstance(record.get("event"), str)
                    or not cls._timestamp(record.get("at"))
                    or not isinstance(record.get("data"), dict)
                ):
                    raise ValueError(f"Invalid ledger listing record: {ledger}")
                if record.get("event") == "run_updated":
                    metadata.update(record["data"])
        return metadata

    @classmethod
    def _read_run_header(cls, ledger: Path) -> dict[str, Any]:
        with ledger.open("rb") as stream:
            line = stream.readline()
        if not line.endswith(b"\n"):
            raise ValueError(f"Ledger has no complete first record: {ledger}")
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"Corrupt ledger header: {ledger}") from error
        data = record.get("data") if isinstance(record, dict) else None
        metadata = data.get("run") if isinstance(data, dict) else None
        if (
            not isinstance(record, dict)
            or record.get("seq") != 1
            or record.get("event") != "run_created"
            or not cls._timestamp(record.get("at"))
            or not isinstance(data, dict)
            or data.get("format_version") != FORMAT_VERSION
            or not isinstance(metadata, dict)
            or metadata.get("run_id") != record.get("run_id")
            or ledger.parent.name != record.get("run_id")
            or metadata.get("task_id") != ledger.parent.parent.parent.name
        ):
            raise ValueError(f"Invalid ledger header: {ledger}")
        return dict(metadata)

    @classmethod
    def read_only_snapshot(cls, path, run_id):
        root = Path(path).resolve()
        cls._safe(run_id, "run_id")
        ledgers = (
            sorted((root / "tasks").glob(f"*/runs/{run_id}/ledger.jsonl"))
            if (root / "tasks").is_dir()
            else []
        )
        for ledger in ledgers:
            try:
                ledger.resolve(strict=True).relative_to(root)
            except ValueError as error:
                raise ValueError(
                    f"Run ledger escapes the state root: {ledger}"
                ) from error
        if not ledgers:
            raise KeyError(f"Unknown run {run_id}")
        if len(ledgers) != 1:
            raise ValueError(f"Ambiguous run {run_id}: found {len(ledgers)} ledgers")
        state = cls._read_path(ledgers[0])
        return JournalSnapshot(
            deepcopy(state.run),
            tuple(deepcopy(op) for op in state.operations.values()),
            tuple(deepcopy(event) for event in state.events),
            state.last_seq,
        )

    def snapshot(self, run_id):
        return self.read_only_snapshot(self.path, run_id)

    def operations(self, run_id):
        with self._lock(run_id):
            return [
                deepcopy(operation)
                for operation in self._load(run_id).operations.values()
            ]

    def _operation(self, operation_id: str) -> tuple[str, dict[str, Any]]:
        with self._index_lock:
            run_id = self._operation_runs.get(operation_id)
        if run_id is not None:
            return run_id, self._load(run_id).operations[operation_id]
        # Runtime operation IDs begin with their run ID. This permits a direct
        # selected-run load after process restart without scanning unrelated
        # histories or opening their payloads. Bare IDs remain usable while
        # their run is already loaded (as in direct Journal tests).
        candidate_id = operation_id.split(":", 1)[0]
        if candidate_id == operation_id or _SAFE_ID.fullmatch(candidate_id) is None:
            raise KeyError(operation_id)
        state = self._load(candidate_id)
        if operation_id not in state.operations:
            raise KeyError(operation_id)
        run_id = candidate_id
        with self._index_lock:
            self._operation_runs[operation_id] = run_id
        return run_id, state.operations[operation_id]

    def get(self, operation_id):
        try:
            _run_id, operation = self._operation(operation_id)
        except KeyError:
            return None
        return deepcopy(operation)

    def confirmed(self, operation_id):
        try:
            run_id, _operation = self._operation(operation_id)
        except KeyError:
            return None
        with self._index_lock:
            cached = self._states.get(run_id)
            if cached is not None and cached.poisoned is not None:
                raise RuntimeError(
                    f"Ledger durability for {run_id} was not confirmed"
                ) from cached.poisoned
        snapshot = self.read_only_snapshot(self.path, run_id)
        return next(
            (row for row in snapshot.operations if row["id"] == operation_id), None
        )

    def begin(
        self,
        *,
        operation_id,
        run_id,
        scope,
        ordinal,
        kind,
        name,
        fingerprint,
        inputs,
        limit,
    ):
        with self._lock(run_id):
            state = self._load(run_id)
            if len(state.operations) >= limit:
                from .errors import BudgetExceeded

                raise BudgetExceeded(f"Run reached its {limit} operation budget")
            if operation_id in state.operations:
                raise ValueError(f"Operation already exists: {operation_id}")
            preset = enforcement = None
            if kind == "provider" and isinstance(inputs, dict):
                values = inputs.get("value")
                if inputs.get("$botpipe") == "dict" and isinstance(values, dict):
                    candidate = values.get("operation")
                    if candidate in {"run", "query", "generate"}:
                        preset = candidate
                    enforcement = {
                        "status": "requested",
                        "policy": values.get("policy"),
                        "tools": values.get("tools"),
                        "settings": values.get("settings"),
                    }
            run_dir = self._ledger_path(run_id).parent
            durable_inputs = self._payload(run_dir, operation_id, "inputs", inputs)
            operation = {
                "id": operation_id,
                "run_id": run_id,
                "scope": scope,
                "ordinal": ordinal,
                "kind": kind,
                "name": name,
                "fingerprint": fingerprint,
                "inputs": durable_inputs,
                "status": "started",
                "result": None,
                "error": None,
                "response": None,
                "thread_id": None,
                "turn_id": None,
                "preset": preset,
                "enforcement": enforcement,
                "probe_hash": None,
                "started_at": now(),
                "finished_at": None,
            }
            self._append_locked(
                run_id,
                "operation_started",
                {"kind": kind, "name": name, "operation": operation},
                operation_id,
            )
            with self._index_lock:
                previous = self._operation_runs.setdefault(operation_id, run_id)
                if previous != run_id:
                    raise ValueError(f"Ambiguous operation {operation_id}")

    def _checkpoint(self, operation_id, event, expected, **values):
        run_id, _operation = self._operation(operation_id)
        with self._lock(run_id):
            operation = self._load(run_id).operations[operation_id]
            target = {
                "operation_completed": "completed",
                "operation_failed": "failed",
                "operation_response": "response",
                "human_input_requested": "waiting",
            }[event]
            comparable = {
                key: value for key, value in values.items() if key != "session_key"
            }
            if operation["status"] == target and all(
                operation.get(k) == v for k, v in comparable.items()
            ):
                return
            if operation["status"] not in expected:
                raise RuntimeError(
                    f"Operation {operation_id} changed from expected state {tuple(expected)!r} to {operation['status']!r}"
                )
            run_dir = self._ledger_path(run_id).parent
            response = values.get("response")
            if (
                event == "operation_response"
                and operation["kind"] == "provider"
                and isinstance(response, dict)
                and isinstance(response.get("text"), str)
            ):
                generation = response.get("generation", 0)
                attempt = generation + 1 if isinstance(generation, int) else 1
                path = (
                    run_dir
                    / "operations"
                    / self._operation_component(operation_id)
                    / "attempts"
                    / str(attempt)
                    / "response.md"
                )
                content = response["text"].encode("utf-8")
                self._publish_owned(run_dir, path, content)
                values = {
                    **values,
                    "response": {
                        **response,
                        "text": {
                            "$ledger_text": self._reference(run_dir, path, content)
                        },
                    },
                }
            durable = {
                key: self._payload(run_dir, operation_id, key, value)
                for key, value in values.items()
            }
            self._append_locked(run_id, event, durable, operation_id)

    def finish(self, operation_id, result):
        self._checkpoint(
            operation_id,
            "operation_completed",
            ("started", "response"),
            result=result,
            error=None,
        )

    def fail(self, operation_id, error):
        self._checkpoint(
            operation_id, "operation_failed", ("started", "response"), error=error
        )

    def response(self, operation_id, response, session_key=None):
        self._checkpoint(
            operation_id,
            "operation_response",
            ("started", "waiting", "response"),
            response=response,
            session_key=session_key,
        )

    def wait_input(self, operation_id, data):
        self._checkpoint(
            operation_id, "human_input_requested", ("started", "waiting"), response=data
        )

    def provider_metadata(
        self,
        operation_id,
        *,
        thread_id=None,
        turn_id=None,
        preset=None,
        enforcement=None,
        probe_hash=None,
    ):
        values = {
            key: value
            for key, value in {
                "thread_id": thread_id,
                "turn_id": turn_id,
                "preset": preset,
                "enforcement": enforcement,
                "probe_hash": probe_hash,
            }.items()
            if value is not None
        }
        if not values:
            return
        if any(
            key != "enforcement" and not isinstance(value, str)
            for key, value in values.items()
        ):
            raise TypeError("Provider metadata identifiers must be strings")
        if preset is not None and preset not in {"run", "query", "generate"}:
            raise ValueError("Provider preset is invalid")
        json.dumps(values, allow_nan=False)
        run_id, operation = self._operation(operation_id)
        if operation["kind"] != "provider":
            raise ValueError("Provider metadata belongs only to provider operations")
        with self._lock(run_id):
            current = self._load(run_id).operations[operation_id]
            changes = {
                key: value for key, value in values.items() if current.get(key) != value
            }
            if changes:
                self._append_locked(run_id, "provider_metadata", changes, operation_id)

    def prepare_attempt(self, operation_id: str, attempt: int, request: dict[str, Any]):
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if not isinstance(request, dict):
            raise TypeError("attempt request must be a dict")
        run_id, operation = self._operation(operation_id)
        if operation["kind"] != "provider":
            raise ValueError("Attempts belong only to provider operations")
        with self._lock(run_id):
            state, key = self._load(run_id), (operation_id, attempt)
            prompt = request.get("prompt")
            if not isinstance(prompt, str):
                raise TypeError("attempt request prompt must be text")
            clean = {name: value for name, value in request.items() if name != "prompt"}
            run_dir = self._ledger_path(run_id).parent
            attempt_dir = (
                run_dir
                / "operations"
                / self._operation_component(operation_id)
                / "attempts"
                / str(attempt)
            )
            prompt_content = prompt.encode("utf-8")
            request_content = (
                json.dumps(
                    clean, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
                ).encode("utf-8")
                + b"\n"
            )
            prompt_path, request_path = (
                attempt_dir / "prompt.md",
                attempt_dir / "request.json",
            )
            existing = state.attempts.get(key)
            if existing is None:
                # A crash may publish these files before their referencing
                # attempt_prepared record. They have no authority and must not
                # pin the next safely prepared request to orphaned bytes.
                for path, content in (
                    (prompt_path, prompt_content),
                    (request_path, request_content),
                ):
                    if path.is_symlink() or (
                        path.exists() and path.read_bytes() != content
                    ):
                        path.unlink()
            self._publish_owned(run_dir, prompt_path, prompt_content)
            self._publish_owned(run_dir, request_path, request_content)
            prepared = {
                "attempt": attempt,
                "prompt": self._reference(run_dir, prompt_path, prompt_content),
                "request": self._reference(run_dir, request_path, request_content),
            }
            if existing is not None:
                if any(existing.get(name) != value for name, value in prepared.items()):
                    raise ValueError(
                        f"Attempt {operation_id}/{attempt} was already prepared differently"
                    )
                return deepcopy(existing)
            self._append_locked(run_id, "attempt_prepared", prepared, operation_id)
            return deepcopy(prepared)

    def attempt_checkpoint(
        self, operation_id: str, attempt: int, update: dict[str, Any]
    ):
        if not isinstance(update, dict) or not update:
            raise ValueError("attempt checkpoint update must be a non-empty dict")
        run_id, _operation = self._operation(operation_id)
        with self._lock(run_id):
            state = self._load(run_id)
            current = state.attempts.get((operation_id, attempt))
            if current is None:
                raise KeyError(f"Unknown attempt {operation_id}/{attempt}")
            self._validate_attempt_status(operation_id, attempt, current, update)
            update = {
                key: value for key, value in update.items() if current.get(key) != value
            }
            if not update:
                return
            run_dir = self._ledger_path(run_id).parent
            response = update.get("response")
            if isinstance(response, dict) and isinstance(response.get("text"), str):
                content = response["text"].encode("utf-8")
                response_path = (
                    run_dir
                    / "operations"
                    / self._operation_component(operation_id)
                    / "attempts"
                    / str(attempt)
                    / "response.md"
                )
                self._publish_owned(run_dir, response_path, content)
                update["response"] = {
                    **response,
                    "text": {
                        "$ledger_text": self._reference(run_dir, response_path, content)
                    },
                }
            durable = {
                key: self._payload(
                    run_dir, operation_id, f"attempt-{attempt}-{key}", value
                )
                for key, value in update.items()
            }
            self._append_locked(
                run_id,
                "attempt_checkpoint",
                {"attempt": attempt, "update": durable},
                operation_id,
            )

    def attempt(self, operation_id: str, attempt: int):
        try:
            run_id, _operation = self._operation(operation_id)
        except KeyError:
            return None
        with self._lock(run_id):
            value = self._load(run_id).attempts.get((operation_id, attempt))
            return None if value is None else deepcopy(value)

    def event(self, run_id, event, data=None, operation_id=None):
        if not isinstance(event, str) or not event:
            raise ValueError("event name must be non-empty text")
        self._append(run_id, event, data or {}, operation_id)

    def events(self, run_id):
        with self._lock(run_id):
            return [deepcopy(event) for event in self._load(run_id).events]

    def create_budget(self, operation_id, config, observed_at):
        run_id, operation = self._operation(operation_id)
        with self._lock(run_id):
            state = self._load(run_id)
            existing = state.budgets.get(operation_id)
            if existing is not None:
                if {key: existing[key] for key in config} != config:
                    from .errors import ReplayMismatch

                    raise ReplayMismatch("Provider budget limits changed across resume")
                return deepcopy(existing)
            duration = config["max_seconds"]
            started = datetime.fromisoformat(operation["started_at"]).timestamp()
            deadline = None if duration is None else started + duration
            budget = {
                **config,
                "used_turns": 0,
                "deadline": deadline,
                "last_observed": observed_at,
                "remaining_seconds": None
                if deadline is None
                else max(0.0, deadline - observed_at),
            }
            self._append_locked(
                run_id,
                "budget_created",
                {"budget_id": operation_id, "state": budget},
                operation_id,
            )
            return deepcopy(budget)

    def budget(self, operation_id):
        run_id, _operation = self._operation(operation_id)
        with self._lock(run_id):
            state = self._load(run_id).budgets.get(operation_id)
            if state is None:
                raise KeyError(f"Unknown provider budget {operation_id}")
            return deepcopy(state)

    @staticmethod
    def _observed_budget(state, observed_at, remaining_cap):
        from .errors import BudgetExceeded

        if observed_at < state["last_observed"]:
            raise BudgetExceeded(
                "Wall clock moved backwards while enforcing provider deadline"
            )
        updated = dict(state, last_observed=observed_at)
        if state["deadline"] is not None:
            updated["remaining_seconds"] = max(
                0.0,
                min(
                    state["deadline"] - observed_at,
                    state["remaining_seconds"],
                    remaining_cap,
                ),
            )
        return updated

    def observe_budgets(self, run_id, budget_ids, observed_at, remaining_caps):
        with self._lock(run_id):
            state = self._load(run_id)
            updated = {
                budget_id: self._observed_budget(
                    state.budgets[budget_id], observed_at, remaining_caps[budget_id]
                )
                for budget_id in budget_ids
            }
            if updated:
                self._append_locked(
                    run_id, "provider_budgets_observed", {"budget_states": updated}
                )
            return [dict(updated[budget_id]) for budget_id in budget_ids]

    def reserve_budgets(
        self,
        run_id,
        operation_id,
        budget_ids,
        observed_at,
        remaining_caps,
        configured_timeout,
        details,
    ):
        from .errors import BudgetExceeded

        with self._lock(run_id):
            state, updated, reservations = self._load(run_id), {}, []
            for budget_id in budget_ids:
                budget = self._observed_budget(
                    state.budgets[budget_id], observed_at, remaining_caps[budget_id]
                )
                if (
                    budget["remaining_seconds"] is not None
                    and budget["remaining_seconds"] <= 0
                ):
                    raise BudgetExceeded("Provider dispatch deadline exhausted")
                if budget["used_turns"] >= budget["max_turns"]:
                    raise BudgetExceeded(
                        f"Provider dispatch budget exhausted ({budget['used_turns']}/{budget['max_turns']} turns)"
                    )
                budget["used_turns"] += 1
                updated[budget_id] = budget
                reservations.append(
                    {"budget_id": budget_id, "sequence": budget["used_turns"]}
                )
            ceilings = [configured_timeout]
            for budget in updated.values():
                ceilings.extend(
                    value
                    for value in (
                        budget["remaining_seconds"],
                        budget["turn_timeout_seconds"],
                    )
                    if value is not None
                )
            self._append_locked(
                run_id,
                "provider_dispatch_reserved",
                {
                    **details,
                    "timeout_seconds": min(ceilings),
                    "budgets": reservations,
                    "budget_states": updated,
                },
                operation_id,
            )
            return [dict(updated[budget_id]) for budget_id in budget_ids]
