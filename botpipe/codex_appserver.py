"""Thin JSONL adapter for the Codex app-server protocol."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from .capabilities import CapabilityError, CodexCapabilities, probe_codex
from .processes import ProcessContainment


class CodexProtocolError(RuntimeError):
    pass


class CodexTurnError(RuntimeError):
    pass


class _RpcCancelled(RuntimeError):
    pass


_CLOSED = object()
_TOOL_ITEMS = {
    "commandExecution": "shell",
    "fileChange": "apply_patch",
    "mcpToolCall": "mcp",
    "dynamicToolCall": "dynamic",
    "collabAgentToolCall": "collaboration",
    "subAgentActivity": "collaboration",
    "webSearch": "web_search",
    "imageView": "view_image",
    "sleep": "sleep",
    "imageGeneration": "image_generation",
}
_PASSIVE_ITEMS = {
    "userMessage",
    "hookPrompt",
    "agentMessage",
    "functionCallOutput",
    "plan",
    "reasoning",
    "enteredReviewMode",
    "exitedReviewMode",
    "contextCompaction",
}
_TOOL_FEATURES = {
    "shell": ("shell_tool", "unified_exec"),
    "web_search": ("standalone_web_search",),
    "view_image": ("view_image",),
    "sleep": ("sleep_tool",),
    "image_generation": ("image_generation",),
    "collaboration": ("multi_agent",),
    "mcp": ("enable_mcp_apps",),
}
_APPROVAL_REQUESTS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "applyPatchApproval",
    "execCommandApproval",
    "mcpServer/elicitation/request",
}


@dataclass(slots=True)
class _Turn:
    thread_id: str
    turn_id: str
    allowed_tools: tuple[str, ...] | None
    on_event: Callable[[Any], None] | None
    on_checkpoint: Callable[[dict[str, Any]], None] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)
    messages: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    error: BaseException | None = None


def _plain(value: Any, *, label: str) -> Any:
    try:
        encoded = json.dumps(value, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise TypeError(f"{label} must be plain JSON") from exc


def _profile_hash(request: Any, config: Mapping[str, Any]) -> str:
    policy = (
        request.policy.effective()
        if hasattr(request.policy, "effective")
        else request.policy
    )
    policy_value = policy.to_dict() if hasattr(policy, "to_dict") else {}
    value = {
        "workspace": str(Path(request.workspace).resolve()),
        "policy": policy_value,
        "preset": request.preset,
        "tools": request.tools,
        "instructions": request.instructions,
        "output_schema": request.output_schema,
        "config": config,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sandbox(request: Any) -> tuple[str, dict[str, Any]]:
    policy = (
        request.policy.effective()
        if hasattr(request.policy, "effective")
        else request.policy
    )
    mode = (
        getattr(getattr(policy, "sandbox_mode", None), "value", None)
        or "workspace_write"
    )
    network = getattr(getattr(policy, "network", None), "value", None) or "none"
    if request.preset in {"query", "generate"}:
        mode, network = "read_only", "none"
    if mode in {"read_only", "read-only"}:
        return "read-only", {"type": "readOnly", "networkAccess": network == "full"}
    if mode in {"danger_full_access", "danger-full-access"}:
        if network != "full":
            raise CapabilityError("danger-full-access cannot enforce disabled network")
        return "danger-full-access", {"type": "dangerFullAccess"}
    workspace = str(Path(request.workspace).resolve())
    roots = [workspace]
    for path in request.artifacts.values():
        resolved = (
            (Path(request.workspace) / path).resolve()
            if not Path(path).is_absolute()
            else Path(path).resolve()
        )
        parent = str(resolved.parent)
        if parent not in roots:
            roots.append(parent)
    return "workspace-write", {
        "type": "workspaceWrite",
        "writableRoots": roots,
        "networkAccess": network == "full",
        "excludeSlashTmp": True,
        "excludeTmpdirEnvVar": True,
    }


def _tool_config(
    request: Any, capabilities: CodexCapabilities, ambient_mcp: frozenset[str]
) -> dict[str, Any]:
    config = dict(_plain(request.settings or {}, label="settings"))
    forbidden = {"approval_policy", "sandbox_mode", "sandbox_workspace_write"}
    if request.preset in {"query", "generate"}:
        forbidden.add("mcp_servers")
    if request.tools is not None:
        forbidden.update(
            {"features", "tools", "apps", "web_search", "browser_use", "computer_use"}
        )
    prefixes = tuple(forbidden)
    forbidden.update(
        key
        for key in config
        if any(key.startswith(prefix + ".") for prefix in prefixes)
    )
    conflict = forbidden & config.keys()
    if conflict:
        raise CapabilityError(
            "settings cannot override mandatory Codex policy: "
            + ", ".join(sorted(conflict))
        )
    tools = request.tools
    builtin_tools = frozenset(_TOOL_FEATURES) | {"apply_patch"}
    mcp_tools = tuple(tool for tool in (tools or ()) if tool not in builtin_tools)
    if request.preset in {"query", "generate"}:
        config.update(
            {
                f"mcp_servers.{json.dumps(name)}.enabled": False
                for name in sorted(ambient_mcp)
            }
        )
        config["web_search"] = "disabled"
        known_features = {item["name"] for item in capabilities.features}
        for feature in ("apps", "enable_mcp_apps"):
            if feature in known_features:
                config[f"features.{feature}"] = False
    if tools is None:
        return config
    known_features = {item["name"] for item in capabilities.features}
    feature_values = {name: False for name in known_features if "sandbox" not in name}
    for tool in tools:
        family = tool.split(":", 1)[0]
        for feature in _TOOL_FEATURES.get(family, ()):
            if feature in known_features:
                feature_values[feature] = True
    config.update(
        {f"features.{name}": enabled for name, enabled in feature_values.items()}
    )
    config["web_search"] = "live" if "web_search" in tools else "disabled"
    if not mcp_tools:
        config.update(
            {
                f"mcp_servers.{json.dumps(name)}.enabled": False
                for name in sorted(ambient_mcp)
            }
        )
    else:
        allowed_servers = set(mcp_tools)
        missing = allowed_servers - ambient_mcp
        if missing:
            raise CapabilityError(
                "requested MCP servers are not configured: "
                + ", ".join(sorted(missing))
            )
        config.update(
            {
                f"mcp_servers.{json.dumps(name)}.enabled": name in allowed_servers
                for name in sorted(ambient_mcp)
            }
        )
    return config


class CodexAppServerAdapter:
    """One multiplexed Codex app-server process owned by a runtime."""

    name = "codex"

    def __init__(
        self,
        command: str | os.PathLike[str] | Sequence[str] = "codex",
        *,
        env: Mapping[str, str] | None = None,
        state_dir: Path | None = None,
        interrupt_grace_seconds: float = 10.0,
        capabilities: CodexCapabilities | None = None,
    ) -> None:
        self.command: tuple[str, ...]
        if isinstance(command, (str, os.PathLike)):
            executable = str(command)
            self.command = (executable, "app-server", "--listen", "stdio://")
        else:
            self.command = tuple(map(str, command))
            if not self.command:
                raise ValueError("Codex command cannot be empty")
            executable = self.command[0]
        self.executable = executable
        self.env = {str(key): str(value) for key, value in (env or {}).items()}
        self.state_dir = state_dir
        self.interrupt_grace_seconds = float(interrupt_grace_seconds)
        self._capabilities = capabilities
        self._injected_capabilities = capabilities is not None
        self._probe_stat: tuple[str, int, int] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._containment: ProcessContainment | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr: list[bytes] = []
        self._lock = threading.RLock()
        self._startup_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._next_id = 0
        self._pending: dict[int, queue.Queue[Any]] = {}
        self._turns: dict[tuple[str, str], _Turn] = {}
        self._orphan_events: dict[
            tuple[str, str], list[tuple[str, dict[str, Any]]]
        ] = {}
        self._thread_locks: dict[str, Any] = {}
        self._mcp_servers: frozenset[str] = frozenset()
        self._closed = False

    def probe(self) -> CodexCapabilities:
        if self._injected_capabilities:
            assert self._capabilities is not None
            return self._capabilities
        located = (
            shutil.which(self.executable)
            if not Path(self.executable).is_absolute()
            and Path(self.executable).parent == Path(".")
            else None
        )
        path = Path(located or self.executable).expanduser().resolve(strict=True)
        stat = path.stat()
        current = (str(path), stat.st_size, stat.st_mtime_ns)
        if self._probe_stat != current:
            if self._process is not None and self._process.poll() is None:
                self._kill_transport(
                    CodexProtocolError("Codex executable changed during runtime")
                )
                if self._containment is not None:
                    self._containment.close()
                self._process, self._containment = None, None
            self._capabilities = probe_codex(
                self.executable, env=self.env, state_dir=self.state_dir
            )
            self._probe_stat = current
        assert self._capabilities is not None
        return self._capabilities

    def _start(self) -> None:
        with self._startup_lock:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Codex adapter is closed")
                if self._process is not None and self._process.poll() is None:
                    return
                capabilities = self.probe()
                if self._containment is not None:
                    self._containment.close()
                    self._containment = None
                self._orphan_events.clear()
                containment = ProcessContainment.create()
                try:
                    process = subprocess.Popen(
                        self.command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={**os.environ, **self.env},
                        **containment.creation_kwargs,
                    )
                    containment.attach_and_start(process)
                except BaseException:
                    containment.close()
                    raise
                self._process, self._containment = process, containment
                self._reader = threading.Thread(
                    target=self._read_loop, args=(process,), daemon=True
                )
                self._stderr_reader = threading.Thread(
                    target=self._read_stderr, args=(process,), daemon=True
                )
                self._reader.start()
                self._stderr_reader.start()
            try:
                self._rpc(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "botpipe",
                            "title": "Botpipe",
                            "version": "2",
                        },
                        "capabilities": {"experimentalApi": True},
                    },
                    10,
                )
                self._send({"method": "initialized"})
                if "mcpServerStatus/list" in capabilities.methods:
                    inventory = self._rpc(
                        "mcpServerStatus/list",
                        {"limit": 1000, "detail": "toolsAndAuthOnly"},
                        10,
                    )
                    self._mcp_servers = frozenset(
                        str(item["name"])
                        for item in inventory.get("data", ())
                        if isinstance(item, Mapping)
                        and isinstance(item.get("name"), str)
                    )
            except BaseException:
                self._kill_transport(CodexProtocolError("Codex initialization failed"))
                raise

    def _read_stderr(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        for chunk in iter(process.stderr.readline, b""):
            self._stderr.append(chunk[-8192:])
            if len(self._stderr) > 32:
                del self._stderr[:-32]

    def _read_loop(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        failure: BaseException | None = None
        try:
            for raw in iter(process.stdout.readline, b""):
                if len(raw) > 8 * 1024 * 1024:
                    raise CodexProtocolError("app-server message exceeds 8 MiB")
                try:
                    message = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CodexProtocolError(
                        "app-server emitted invalid JSONL"
                    ) from exc
                if not isinstance(message, Mapping):
                    raise CodexProtocolError(
                        "app-server JSONL messages must be objects"
                    )
                self._receive(dict(message))
        except BaseException as exc:  # noqa: BLE001 - reader must wake waiters on every exit
            failure = exc
        if failure is None:
            detail = b"".join(self._stderr).decode(errors="replace").strip()
            failure = CodexProtocolError(
                "app-server closed" + (f": {detail[-2000:]}" if detail else "")
            )
        with self._lock:
            current = self._process is process
            containment = self._containment if current else None
        if current:
            if containment is not None:
                try:
                    containment.ensure_tree_exited(process, grace_seconds=0.1)
                except Exception as cleanup_error:  # noqa: BLE001 - cleanup failure replaces transport failure
                    failure = CodexProtocolError(
                        f"app-server process-tree cleanup failed: {cleanup_error}"
                    )
            self._fail_transport(failure, process=process)

    def _receive(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if request_id is not None and "method" not in message:
            with self._lock:
                pending = self._pending.get(request_id)
            if pending is not None:
                pending.put(message)
            return
        method = message.get("method")
        if isinstance(method, str) and request_id is not None:
            self._answer_server_request(request_id, method)
            return
        if not isinstance(method, str):
            return
        params = message.get("params")
        if not isinstance(params, Mapping):
            params = {}
        thread_id, turn_id = params.get("threadId"), params.get("turnId")
        nested_turn = params.get("turn")
        if not isinstance(turn_id, str) and isinstance(nested_turn, Mapping):
            turn_id = nested_turn.get("id")
        if not isinstance(thread_id, str):
            return
        with self._lock:
            turn = (
                self._turns.get((thread_id, turn_id))
                if isinstance(turn_id, str)
                else None
            )
            if turn is None:
                candidates = [
                    value
                    for (candidate_thread, _), value in self._turns.items()
                    if candidate_thread == thread_id
                ]
                if len(candidates) == 1:
                    turn = candidates[0]
        if turn is None:
            if not isinstance(turn_id, str):
                return
            with self._lock:
                if (
                    len(self._orphan_events) >= 256
                    and (thread_id, turn_id) not in self._orphan_events
                ):
                    self._orphan_events.pop(next(iter(self._orphan_events)))
                events = self._orphan_events.setdefault((thread_id, turn_id), [])
                if len(events) < 128:
                    events.append((method, dict(params)))
            return
        self._record_event(turn, method, dict(params))

    def _answer_server_request(self, request_id: Any, method: str) -> None:
        if method == "mcpServer/elicitation/request":
            result: Any = {"action": "decline"}
        elif method in {"applyPatchApproval", "execCommandApproval"}:
            result = {"decision": "abort"}
        elif method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            result = {"decision": "cancel"}
        elif method in _APPROVAL_REQUESTS:
            self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32001,
                        "message": "Botpipe approval policy is never",
                    },
                }
            )
            return
        else:
            self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Botpipe does not mediate {method}",
                    },
                }
            )
            return
        self._send({"id": request_id, "result": result})

    def _record_event(self, turn: _Turn, method: str, params: dict[str, Any]) -> None:
        event = {"type": method, "data": _plain(params, label="event")}
        with turn.condition:
            if len(turn.events) < 4096:
                turn.events.append(event)
            item = params.get("item")
            if method in {"item/started", "item/completed"} and isinstance(
                item, Mapping
            ):
                kind = item.get("type")
                if (
                    method == "item/completed"
                    and kind == "agentMessage"
                    and isinstance(item.get("text"), str)
                ):
                    turn.messages.append(item["text"])
                tool = _TOOL_ITEMS.get(str(kind))
                if tool is not None and not self._tool_allowed(
                    turn.allowed_tools, tool, item
                ):
                    turn.error = CapabilityError(
                        f"Codex used disallowed tool {tool!r}; evidence: "
                        + json.dumps(
                            {"type": kind, "id": item.get("id")}, sort_keys=True
                        )
                    )
                elif (
                    turn.allowed_tools is not None
                    and isinstance(kind, str)
                    and kind not in _PASSIVE_ITEMS
                    and kind not in _TOOL_ITEMS
                ):
                    turn.error = CapabilityError(
                        f"Codex emitted unclassified item {kind!r} under a tool allowlist; "
                        + "evidence: "
                        + json.dumps(
                            {"type": kind, "id": item.get("id")}, sort_keys=True
                        )
                    )
            if method == "thread/tokenUsage/updated":
                usage = params.get("tokenUsage") or params.get("usage")
                if isinstance(usage, Mapping):
                    turn.usage = dict(usage)
            if method == "error" and not params.get("willRetry"):
                turn.error = CodexTurnError(
                    str(params.get("error") or "Codex turn failed")
                )
            if method == "turn/completed":
                terminal = params.get("turn")
                status = (
                    terminal.get("status") if isinstance(terminal, Mapping) else None
                )
                if status not in (None, "completed") and turn.error is None:
                    turn.error = CodexTurnError(
                        f"Codex turn ended with status {status!r}"
                    )
                turn.completed = True
                if turn.on_checkpoint is not None:
                    try:
                        turn.on_checkpoint({"status": "response_received"})
                    except Exception:  # noqa: BLE001,S110 - best-effort observation
                        pass
            turn.condition.notify_all()
        callback = turn.on_event
        if callback is not None:
            try:
                from .providers import StreamEvent

                callback(StreamEvent(method, dict(params)))
            except BaseException:  # noqa: BLE001,S110 - best-effort observation
                pass

    @staticmethod
    def _tool_allowed(
        allowed: tuple[str, ...] | None, family: str, item: Mapping[str, Any]
    ) -> bool:
        if allowed is None:
            return True
        if family != "mcp":
            name = item.get("tool") if family == "dynamic" else family
            return isinstance(name, str) and name in allowed
        server, tool = item.get("server"), item.get("tool")
        candidates: set[str] = set()
        if isinstance(server, str):
            candidates.add(server)
            candidates.add(f"mcp:{server}")
            if isinstance(tool, str):
                candidates.add(f"mcp:{server}/{tool}")
        return any(name in candidates for name in allowed)

    def _send(self, message: Mapping[str, Any]) -> None:
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        with self._write_lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise CodexProtocolError("app-server is not running")
            try:
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise CodexProtocolError("app-server input closed") from exc

    def _rpc(
        self,
        method: str,
        params: Any,
        timeout: float,
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        response_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            self._pending[request_id] = response_queue
        try:
            self._send({"id": request_id, "method": method, "params": params})
            deadline = time.monotonic() + timeout
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RpcCancelled(f"Codex RPC {method} was cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Codex RPC {method} timed out")
                try:
                    response = response_queue.get(timeout=min(0.1, remaining))
                    break
                except queue.Empty:
                    continue
            if isinstance(response, BaseException):
                raise response
            if "error" in response:
                error = response["error"]
                detail = error.get("message") if isinstance(error, Mapping) else error
                raise CodexProtocolError(f"Codex RPC {method} failed: {detail}")
            result = response.get("result")
            if not isinstance(result, Mapping):
                raise CodexProtocolError(
                    f"Codex RPC {method} returned no object result"
                )
            return dict(result)
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def start_turn(
        self, request: Any, on_event: Callable[[Any], None] | None = None
    ) -> Any:
        capabilities = self.probe()
        capabilities.require(request.preset)
        if request.tools is not None:
            unclassified = capabilities.item_types - _PASSIVE_ITEMS - _TOOL_ITEMS.keys()
            if unclassified:
                raise CapabilityError(
                    "Codex protocol exposes unclassified turn items under a tool allowlist: "
                    + ", ".join(sorted(unclassified))
                )
        self._start()
        config = _tool_config(request, capabilities, self._mcp_servers)
        sandbox_name, sandbox_policy = _sandbox(request)
        profile_hash = _profile_hash(request, config)
        expected_profile = None
        if isinstance(request.checkpoint, Mapping):
            expected_profile = request.checkpoint.get("profile_hash")
        if expected_profile is not None and expected_profile != profile_hash:
            raise CapabilityError(
                "resumed Codex thread has an incompatible execution profile"
            )
        model = getattr(request.policy, "model", None)
        raw_effort = getattr(request.policy, "effort", None)
        effort = getattr(raw_effort, "value", raw_effort)
        if effort and not capabilities.supports_effort:
            raise CapabilityError(
                "installed Codex cannot apply reasoning effort per turn"
            )
        if request.instructions and not capabilities.supports_instructions:
            raise CapabilityError(
                "installed Codex cannot apply instructions when starting and resuming threads"
            )
        enforcement = {
            "approval_policy": "never",
            "sandbox_policy": sandbox_policy,
            "feature_overrides": {
                key.removeprefix("features."): value
                for key, value in config.items()
                if key.startswith("features.")
            },
            "mcp_servers": {
                key.removeprefix("mcp_servers.").removesuffix(".enabled"): bool(value)
                for key, value in config.items()
                if key.startswith("mcp_servers.") and key.endswith(".enabled")
            },
            "allowed_tools": list(request.tools) if request.tools is not None else None,
        }
        common = {
            "cwd": str(Path(request.workspace).resolve()),
            "model": model,
            "approvalPolicy": "never",
            "sandbox": sandbox_name,
            "config": config,
        }
        if request.instructions:
            common["developerInstructions"] = request.instructions
        if request.on_checkpoint is not None:
            request.on_checkpoint(
                {
                    "status": "configured",
                    "profile_hash": profile_hash,
                    "probe_hash": capabilities.probe_hash,
                    "enforcement": enforcement,
                    "sandbox": sandbox_policy,
                    "preset": request.preset,
                    "tools": list(request.tools) if request.tools is not None else None,
                }
            )
        thread_id = request.session_id
        outer_lock: threading.RLock | None = None
        if thread_id is not None:
            outer_lock = self._thread_locks.setdefault(thread_id, threading.RLock())
            outer_lock.acquire()
        if thread_id is None:
            dynamic_tools: list[dict[str, Any]] = []
            result = self._rpc(
                "thread/start",
                {**common, "ephemeral": False, "dynamicTools": dynamic_tools},
                min(10, request.timeout),
            )
        else:
            try:
                result = self._rpc(
                    "thread/resume",
                    {**common, "threadId": thread_id},
                    min(10, request.timeout),
                )
            except CodexProtocolError as exc:
                assert outer_lock is not None
                outer_lock.release()
                from .errors import SessionError

                raise SessionError(
                    f"Codex thread {thread_id!r} could not be resumed: {exc}"
                ) from exc
            except BaseException:
                assert outer_lock is not None
                outer_lock.release()
                raise
        thread = result.get("thread")
        actual_thread = thread.get("id") if isinstance(thread, Mapping) else None
        if not isinstance(actual_thread, str) or not actual_thread:
            if outer_lock is not None:
                outer_lock.release()
            raise CodexProtocolError("thread response contained no thread id")
        if thread_id is not None and actual_thread != thread_id:
            assert outer_lock is not None
            outer_lock.release()
            raise CodexProtocolError("thread/resume returned a different thread id")
        thread_id = actual_thread
        if outer_lock is None:
            outer_lock = self._thread_locks.setdefault(thread_id, threading.RLock())
            outer_lock.acquire()
        try:
            if request.on_checkpoint is not None:
                request.on_checkpoint(
                    {
                        "status": "thread_bound",
                        "session_id": thread_id,
                        "profile_hash": profile_hash,
                        "probe_hash": capabilities.probe_hash,
                        "enforcement": enforcement,
                    }
                )
        except BaseException:
            outer_lock.release()
            raise
        thread_lock = outer_lock
        with thread_lock:
            params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": request.prompt}],
                "approvalPolicy": "never",
                "sandboxPolicy": sandbox_policy,
            }
            if (
                request.output_schema is not None
                and capabilities.supports_output_schema
            ):
                params["outputSchema"] = _plain(
                    request.output_schema, label="output schema"
                )
            elif request.output_schema is not None:
                params["input"][0]["text"] += (
                    "\n\nReturn only JSON matching this schema:\n"
                    + json.dumps(request.output_schema, sort_keys=True)
                )
            if model:
                params["model"] = model
            if effort:
                params["effort"] = effort
            if request.cancel_event is not None and request.cancel_event.is_set():
                outer_lock.release()
                from .providers import ProviderInterruptedError

                raise ProviderInterruptedError("Codex turn cancelled before dispatch")
            try:
                if request.on_checkpoint is not None:
                    request.on_checkpoint(
                        {
                            "status": "turn_intent",
                            "session_id": thread_id,
                            "profile_hash": profile_hash,
                            "probe_hash": capabilities.probe_hash,
                            "enforcement": enforcement,
                        }
                    )
                started = self._rpc(
                    "turn/start",
                    params,
                    min(10, request.timeout),
                    request.cancel_event,
                )
                turn_value = started.get("turn")
                turn_id = (
                    turn_value.get("id") if isinstance(turn_value, Mapping) else None
                )
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexProtocolError("turn/start returned no turn id")
                if request.on_checkpoint is not None:
                    request.on_checkpoint(
                        {
                            "status": "turn_acknowledged",
                            "session_id": thread_id,
                            "turn_id": turn_id,
                            "profile_hash": profile_hash,
                            "probe_hash": capabilities.probe_hash,
                            "enforcement": enforcement,
                        }
                    )
            except BaseException as exc:
                self._kill_transport(
                    CodexTurnError("turn/start acknowledgement was not durable"),
                    grace_seconds=0.1,
                )
                outer_lock.release()
                if isinstance(exc, _RpcCancelled):
                    from .providers import ProviderInterruptedError

                    raise ProviderInterruptedError(
                        "Codex turn cancelled before acknowledgement; transport cleaned up"
                    ) from exc
                if isinstance(exc, TimeoutError):
                    from .providers import ProviderTimeoutError

                    raise ProviderTimeoutError(
                        f"Codex turn start timed out after {min(10, request.timeout):g} seconds"
                    ) from exc
                raise
            turn = _Turn(
                thread_id,
                turn_id,
                request.tools,
                on_event or request.on_event,
                request.on_checkpoint,
            )
            with self._lock:
                self._turns[(thread_id, turn_id)] = turn
                early = self._orphan_events.pop((thread_id, turn_id), ())
            for method, event_params in early:
                self._record_event(turn, method, event_params)
            deadline = time.monotonic() + request.timeout
            try:
                with turn.condition:
                    while not turn.completed and turn.error is None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        turn.condition.wait(min(remaining, 0.1))
                        if (
                            request.cancel_event is not None
                            and request.cancel_event.is_set()
                        ):
                            break
                if (
                    request.cancel_event is not None
                    and request.cancel_event.is_set()
                    and not turn.completed
                ):
                    self._stop_turn(turn, "Codex turn cancelled")
                    from .providers import ProviderInterruptedError

                    raise ProviderInterruptedError("Codex turn cancelled after cleanup")
                if not turn.completed and turn.error is None:
                    self._stop_turn(turn, "Codex turn timed out")
                    from .providers import ProviderTimeoutError

                    raise ProviderTimeoutError(
                        f"Codex turn timed out after {request.timeout:g} seconds"
                    )
                if turn.error is not None:
                    if isinstance(turn.error, CapabilityError):
                        self._stop_turn(turn, str(turn.error))
                    raise turn.error
                if not turn.messages:
                    raise CodexProtocolError(
                        "Codex completed without an assistant message"
                    )
                from .providers import ProviderResponse

                return ProviderResponse(
                    turn.messages[-1],
                    thread_id,
                    dict(turn.usage),
                    {
                        "provider": "codex",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "probe_hash": capabilities.probe_hash,
                        "profile_hash": profile_hash,
                        "enforcement": enforcement,
                        "audit": list(turn.events),
                    },
                )
            finally:
                with self._lock:
                    self._turns.pop((thread_id, turn_id), None)
                outer_lock.release()

    def recover_turn(
        self, request: Any, *, thread_id: str, turn_id: str
    ) -> tuple[str, Any | None]:
        """Interrogate native thread history without dispatching model input."""
        capabilities = self.probe()
        if "thread/read" not in capabilities.methods:
            return "unknown", None
        self._start()
        config = _tool_config(request, capabilities, self._mcp_servers)
        sandbox_name, _ = _sandbox(request)
        common = {
            "threadId": thread_id,
            "cwd": str(Path(request.workspace).resolve()),
            "approvalPolicy": "never",
            "sandbox": sandbox_name,
            "config": config,
        }
        model = getattr(request.policy, "model", None)
        if model:
            common["model"] = model
        try:
            with self._thread_locks.setdefault(thread_id, threading.RLock()):
                self._rpc("thread/resume", common, min(10, request.timeout))
                result = self._rpc(
                    "thread/read",
                    {"threadId": thread_id, "includeTurns": True},
                    min(10, request.timeout),
                )
        except CodexProtocolError as exc:
            from .errors import SessionError

            raise SessionError(
                f"Codex thread {thread_id!r} could not be resumed: {exc}"
            ) from exc
        thread = result.get("thread")
        turns = thread.get("turns") if isinstance(thread, Mapping) else None
        if not isinstance(turns, list):
            return "unknown", None
        match = next(
            (
                turn
                for turn in turns
                if isinstance(turn, Mapping) and turn.get("id") == turn_id
            ),
            None,
        )
        if match is None:
            return "unknown", None
        status = match.get("status")
        if status == "completed":
            messages = [
                item.get("text")
                for item in match.get("items", ())
                if isinstance(item, Mapping)
                and item.get("type") == "agentMessage"
                and isinstance(item.get("text"), str)
            ]
            if not messages:
                return "unknown", None
            from .providers import ProviderResponse

            return "completed", ProviderResponse(
                str(messages[-1]),
                thread_id,
                {},
                {
                    "provider": "codex",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "recovered": True,
                },
            )
        if status in {"inProgress", "running", "pending"}:
            return "running", None
        if status in {"failed", "interrupted", "cancelled"}:
            return "stopped", None
        return "unknown", None

    def interrupt(self, thread_id: str, turn_id: str) -> None:
        self._rpc(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            min(5.0, self.interrupt_grace_seconds),
        )

    def _stop_turn(self, turn: _Turn, reason: str) -> None:
        try:
            self.interrupt(turn.thread_id, turn.turn_id)
        except Exception:  # noqa: BLE001,S110 - escalation below is authoritative
            pass
        deadline = time.monotonic() + self.interrupt_grace_seconds
        with turn.condition:
            while not turn.completed and time.monotonic() < deadline:
                turn.condition.wait(min(0.1, deadline - time.monotonic()))
        if not turn.completed:
            self._kill_transport(CodexTurnError(reason), grace_seconds=0.1)

    def _fail_transport(
        self, error: BaseException, *, process: subprocess.Popen[bytes] | None = None
    ) -> None:
        with self._lock:
            if process is not None and self._process is not process:
                return
            pending, turns = list(self._pending.values()), list(self._turns.values())
        for waiter in pending:
            try:
                waiter.put_nowait(error)
            except queue.Full:
                pass
        for turn in turns:
            with turn.condition:
                if turn.error is None:
                    turn.error = error
                turn.condition.notify_all()

    def _kill_transport(
        self, error: BaseException, *, grace_seconds: float = 0.1
    ) -> None:
        self._fail_transport(error)
        process, containment = self._process, self._containment
        if process is not None and containment is not None and process.poll() is None:
            containment.terminate(process, grace_seconds=grace_seconds)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._kill_transport(CodexProtocolError("Codex adapter closed"))
        process, containment = self._process, self._containment
        if process is not None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                if containment is not None:
                    containment.terminate(process, grace_seconds=0.1)
            if containment is not None:
                containment.ensure_tree_exited(process, grace_seconds=0.1)
        if containment is not None:
            containment.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "CodexAppServerAdapter",
    "CodexProtocolError",
    "CodexTurnError",
]
