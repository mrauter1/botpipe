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
from contextlib import ExitStack
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
    # This is deliberately a reviewed list of feature flags that expose a
    # model-facing tool.  Feature discovery tells us which entries the
    # installed Codex accepts; unrelated discovered features retain their
    # native value.
    "shell": (
        "shell_tool",
        "unified_exec",
        "unified_exec_tty",
    ),
    "web_search": (
        "standalone_web_search",
        "search_tool",
        "web_search_cached",
        "web_search_request",
    ),
    "view_image": ("view_image",),
    "sleep": ("sleep_tool",),
    "image_generation": ("image_generation",),
    "collaboration": (
        "multi_agent",
        "multi_agent_v2",
        "multi_agent_mode",
        "collaboration_modes",
        "enable_fanout",
    ),
    "mcp": (),
    "request_user_input": ("default_mode_request_user_input",),
    "update_plan": (),
}
_DISABLED_ONLY_TOOL_FEATURES = frozenset(
    {
        # These expose alternate execution/catalog surfaces that Botpipe does
        # not yet classify as one of its allowlisted tool families.
        "apps",
        "artifact",
        "browser_use",
        "browser_use_external",
        "browser_use_full_cdp_access",
        "code_mode",
        "code_mode_host",
        "code_mode_only",
        "codex_apps_mcp_2026_07_28",
        "computer_use",
        "deferred_executor",
        "enable_mcp_apps",
        "hooks",
        "in_app_browser",
        "in_app_local_automation",
        "js_repl",
        "js_repl_tools_only",
        "plugin_hooks",
        "plugins",
        "recommended_plugins",
        "remote_plugin",
        "request_permissions_tool",
        "skill_mcp_dependency_install",
        "tool_search",
        "tool_suggest",
        "unavailable_dummy_tools",
        "workspace_dependencies",
    }
)
_TOOL_ENABLING_FEATURES = frozenset(
    feature for features in _TOOL_FEATURES.values() for feature in features
) | _DISABLED_ONLY_TOOL_FEATURES
_TOOL_EVENTS = {
    "turn/plan/updated": "update_plan",
    "item/tool/requestUserInput": "request_user_input",
    "item/tool/call": "dynamic",
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
    tools_observed: bool = False
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
        for feature in _DISABLED_ONLY_TOOL_FEATURES:
            if feature in known_features:
                config[f"features.{feature}"] = False
    if tools is None:
        return config
    known_features = {item["name"] for item in capabilities.features}
    feature_values = {
        name: False for name in known_features & _TOOL_ENABLING_FEATURES
    }
    for tool in tools:
        family = tool.split(":", 1)[0]
        for feature in _TOOL_FEATURES.get(family, ()):
            if feature in known_features:
                feature_values[feature] = True
    config.update(
        {f"features.{name}": enabled for name, enabled in feature_values.items()}
    )
    config["web_search"] = "live" if "web_search" in tools else "disabled"
    config["tools.experimental_request_user_input.enabled"] = "request_user_input" in tools
    config["tools.update_plan.enabled"] = "update_plan" in tools
    if not mcp_tools:
        config.update(
            {
                f"mcp_servers.{json.dumps(name)}.enabled": False
                for name in sorted(ambient_mcp)
            }
        )
    else:
        allowed_servers = {
            name.removeprefix("mcp:").split("/", 1)[0] for name in mcp_tools
        }
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
        self._thread_profiles: dict[str, str] = {}
        self._mcp_servers: frozenset[str] = frozenset()
        self._closed = False

    def probe(self, *, deadline: float | None = None) -> CodexCapabilities:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Codex capability probe timed out")
        if self._injected_capabilities:
            assert self._capabilities is not None
            return self._capabilities
        located = (
            shutil.which(self.executable)
            if not Path(self.executable).is_absolute()
            and Path(self.executable).parent == Path(".")
            else None
        )
        try:
            path = Path(located or self.executable).expanduser().resolve(strict=True)
        except OSError as exc:
            raise CapabilityError(
                f"Codex executable {self.executable!r} is unavailable: {exc}. "
                "Install Codex or configure codex.path to an executable."
            ) from exc
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
                self.executable,
                env=self.env,
                state_dir=self.state_dir,
                deadline=deadline,
            )
            self._probe_stat = current
        assert self._capabilities is not None
        return self._capabilities

    def _start(self, *, deadline: float | None = None) -> None:
        lock_timeout = -1 if deadline is None else max(0.0, deadline - time.monotonic())
        if not self._startup_lock.acquire(timeout=lock_timeout):
            raise TimeoutError("Codex initialization timed out")
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Codex adapter is closed")
                if self._process is not None and self._process.poll() is None:
                    return
                capabilities = self.probe(deadline=deadline)
                if self._containment is not None:
                    self._containment.close()
                    self._containment = None
                self._orphan_events.clear()
                self._thread_profiles.clear()
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
                    deadline=deadline,
                )
                self._send({"method": "initialized"})
                if os.name == "nt" and "windowsSandbox/readiness" in capabilities.methods:
                    readiness = self._rpc(
                        "windowsSandbox/readiness", None, 10, deadline=deadline
                    )
                    if readiness.get("status") != "ready":
                        raise CapabilityError(
                            "Codex Windows sandbox is not ready "
                            f"({readiness.get('status', 'unknown')}); "
                            "complete or update Codex's Windows sandbox setup "
                            "before running Botpipe"
                        )
                if "mcpServerStatus/list" in capabilities.methods:
                    inventory = self._rpc(
                        "mcpServerStatus/list",
                        {"limit": 1000, "detail": "toolsAndAuthOnly"},
                        10,
                        deadline=deadline,
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
        finally:
            self._startup_lock.release()

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
                    with self._lock:
                        affected = [
                            turn for turn in self._turns.values() if not turn.completed
                        ]
                    self._checkpoint_cleanup_failure(affected, failure)
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
            if method not in _TOOL_EVENTS:
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
            event_tool = _TOOL_EVENTS.get(method)
            if event_tool is not None:
                turn.tools_observed = True
                if not self._tool_allowed(turn.allowed_tools, event_tool, params):
                    turn.error = CapabilityError(
                        f"Codex used disallowed tool {event_tool!r}; evidence: {method}"
                    )
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
                if tool is not None:
                    turn.tools_observed = True
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
            if method == "error" and not params.get("willRetry") and turn.error is None:
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
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        response_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            self._pending[request_id] = response_queue
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Codex RPC {method} timed out before dispatch")
            self._send({"id": request_id, "method": method, "params": params})
            rpc_deadline = time.monotonic() + timeout
            if deadline is not None:
                rpc_deadline = min(rpc_deadline, deadline)
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise _RpcCancelled(f"Codex RPC {method} was cancelled")
                remaining = rpc_deadline - time.monotonic()
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
        from .providers import ProviderTimeoutError

        deadline = (
            request.deadline
            if request.deadline is not None
            else time.monotonic() + request.timeout
        )

        def timed_out() -> ProviderTimeoutError:
            return ProviderTimeoutError(
                f"Codex turn timed out (dispatch budget: {request.timeout:g} seconds)"
            )

        def remaining(limit: float | None = None) -> float:
            value = deadline - time.monotonic()
            if limit is not None:
                value = min(limit, value)
            if value <= 0:
                raise timed_out()
            return value

        try:
            capabilities = self.probe(deadline=deadline)
        except TimeoutError as exc:
            raise timed_out() from exc
        capabilities.require(request.preset)
        try:
            self._start(deadline=deadline)
        except TimeoutError as exc:
            raise timed_out() from exc
        config = _tool_config(request, capabilities, self._mcp_servers)
        sandbox_name, sandbox_policy = _sandbox(request)
        profile_hash = _profile_hash(request, config)
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
            "sandbox": f"codex:{sandbox_name}",
            "network": (
                "codex:on"
                if sandbox_name == "danger-full-access" or sandbox_policy.get("networkAccess")
                else "codex:off"
            ),
            "tools": (
                {"mode": "defaults"}
                if request.tools is None
                else {
                    "mode": "allowlist",
                    "allowed": list(request.tools),
                    "disabled_via": "codex-features",
                }
            ),
            "codex_version": capabilities.version,
            "approval_policy": "never",
            "sandbox_policy": sandbox_policy,
            "feature_overrides": {
                key.removeprefix("features."): value
                for key, value in config.items()
                if key.startswith("features.")
            },
            "tool_overrides": {
                key.removeprefix("tools."): value
                for key, value in config.items()
                if key.startswith("tools.")
            },
            "mcp_servers": {
                key.removeprefix("mcp_servers.").removesuffix(".enabled"): bool(value)
                for key, value in config.items()
                if key.startswith("mcp_servers.") and key.endswith(".enabled")
            },
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
        remaining()
        with ExitStack() as thread_scope:
            thread_id = request.session_id
            outer_lock: threading.RLock | None = None
            if thread_id is not None:
                outer_lock = self._thread_locks.setdefault(thread_id, threading.RLock())
                if not outer_lock.acquire(timeout=remaining()):
                    raise timed_out()
                thread_scope.callback(outer_lock.release)
            if thread_id is None:
                dynamic_tools: list[dict[str, Any]] = []
                try:
                    result = self._rpc(
                        "thread/start",
                        {**common, "ephemeral": False, "dynamicTools": dynamic_tools},
                        remaining(10),
                        deadline=deadline,
                    )
                except TimeoutError as exc:
                    raise timed_out() from exc
            else:
                try:
                    previous_profile = self._thread_profiles.get(thread_id)
                    if previous_profile is not None and previous_profile != profile_hash:
                        if "thread/unsubscribe" not in capabilities.methods:
                            raise CapabilityError(
                                "thread/unsubscribe is required to change a loaded thread's configuration"
                            )
                        # Codex ignores resume config while a thread has subscribers.
                        # Detach this idle session so resume reloads the same history.
                        self._rpc(
                            "thread/unsubscribe",
                            {"threadId": thread_id},
                            remaining(10),
                            deadline=deadline,
                        )
                    result = self._rpc(
                        "thread/resume",
                        {**common, "threadId": thread_id},
                        remaining(10),
                        deadline=deadline,
                    )
                except TimeoutError as exc:
                    raise timed_out() from exc
                except CodexProtocolError as exc:
                    from .errors import SessionError

                    raise SessionError(
                        f"Codex thread {thread_id!r} could not be resumed: {exc}"
                    ) from exc
            thread = result.get("thread")
            actual_thread = thread.get("id") if isinstance(thread, Mapping) else None
            if not isinstance(actual_thread, str) or not actual_thread:
                raise CodexProtocolError("thread response contained no thread id")
            if thread_id is not None and actual_thread != thread_id:
                raise CodexProtocolError("thread/resume returned a different thread id")
            thread_id = actual_thread
            if outer_lock is None:
                outer_lock = self._thread_locks.setdefault(thread_id, threading.RLock())
                if not outer_lock.acquire(timeout=remaining()):
                    raise timed_out()
                thread_scope.callback(outer_lock.release)
            self._thread_profiles[thread_id] = profile_hash
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
            remaining()
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
                from .providers import ProviderInterruptedError

                raise ProviderInterruptedError("Codex turn cancelled before dispatch")
            with self._lock:
                orphan_baseline = {
                    key for key in self._orphan_events if key[0] == thread_id
                }
            acknowledged_turn_id: str | None = None
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
                    remaining(10),
                    request.cancel_event,
                    deadline=deadline,
                )
                turn_value = started.get("turn")
                turn_id = (
                    turn_value.get("id") if isinstance(turn_value, Mapping) else None
                )
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexProtocolError("turn/start returned no turn id")
                acknowledged_turn_id = turn_id
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
                try:
                    self._kill_transport(
                        CodexTurnError("turn/start acknowledgement was not durable"),
                        grace_seconds=0.1,
                    )
                except BaseException as cleanup_exc:
                    if request.on_checkpoint is not None:
                        request.on_checkpoint(
                            {
                                "cleanup": {
                                    "status": "incomplete",
                                    "error": str(cleanup_exc),
                                }
                            }
                        )
                    raise
                reader = self._reader
                if reader is not None and reader is not threading.current_thread():
                    reader.join(timeout=min(1.0, self.interrupt_grace_seconds))
                    if reader.is_alive():
                        audit_error = CodexProtocolError(
                            "app-server event stream did not drain after cleanup"
                        )
                        if request.on_checkpoint is not None:
                            request.on_checkpoint(
                                {
                                    "cleanup": {
                                        "status": "incomplete",
                                        "error": str(audit_error),
                                    }
                                }
                            )
                        raise audit_error
                # A verified transport-tree teardown makes the unknown
                # pre-acknowledgement dispatch durably stopped.  Audit any
                # events that arrived before the RPC response was lost.
                pre_ack = _Turn(thread_id, "pre-ack", request.tools, None)
                with self._lock:
                    orphaned = [
                        (key, list(events))
                        for key, events in self._orphan_events.items()
                        if key[0] == thread_id
                        and key not in orphan_baseline
                        and (
                            acknowledged_turn_id is None
                            or key[1] == acknowledged_turn_id
                        )
                    ]
                    for key, _events in orphaned:
                        self._orphan_events.pop(key, None)
                if len(orphaned) == 1:
                    pre_ack.turn_id = orphaned[0][0][1]
                for (_event_thread, _event_turn), events in orphaned:
                    for method, event_params in events:
                        self._record_event(pre_ack, method, event_params)
                enforcement["audit"] = (
                    "tool-policy-violation"
                    if isinstance(pre_ack.error, CapabilityError)
                    else "tool-calls-observed"
                    if pre_ack.tools_observed
                    else "no-tool-calls-observed"
                )
                stopped_checkpoint: dict[str, Any] = {
                    "status": "failed",
                    "error": str(pre_ack.error or exc),
                    "cleanup": {"status": "completed"},
                    "enforcement": enforcement,
                    "audit": list(pre_ack.events),
                }
                if isinstance(pre_ack.error, CapabilityError):
                    stopped_checkpoint["policy_error"] = True
                if (
                    len(orphaned) == 1
                    and pre_ack.completed
                    and pre_ack.error is None
                    and pre_ack.messages
                ):
                    if request.on_checkpoint is not None:
                        request.on_checkpoint(
                            {
                                "status": "response_received",
                                "session_id": thread_id,
                                "turn_id": pre_ack.turn_id,
                                "enforcement": enforcement,
                                "audit": list(pre_ack.events),
                            }
                        )
                    from .providers import ProviderResponse

                    return ProviderResponse(
                        pre_ack.messages[-1],
                        thread_id,
                        dict(pre_ack.usage),
                        {
                            "provider": "codex",
                            "codex_version": capabilities.version,
                            "thread_id": thread_id,
                            "turn_id": pre_ack.turn_id,
                            "probe_hash": capabilities.probe_hash,
                            "profile_hash": profile_hash,
                            "enforcement": enforcement,
                            "audit": list(pre_ack.events),
                            "recovered_from_lost_ack": True,
                        },
                    )
                if request.on_checkpoint is not None:
                    request.on_checkpoint(stopped_checkpoint)
                if pre_ack.error is not None:
                    raise pre_ack.error
                if isinstance(exc, _RpcCancelled):
                    from .providers import ProviderInterruptedError

                    raise ProviderInterruptedError(
                        "Codex turn cancelled before acknowledgement; transport cleaned up"
                    ) from exc
                if isinstance(exc, TimeoutError):
                    from .providers import ProviderTimeoutError

                    raise ProviderTimeoutError(
                        f"Codex turn start timed out (dispatch budget: {request.timeout:g} seconds)"
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
                        "codex_version": capabilities.version,
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "probe_hash": capabilities.probe_hash,
                        "profile_hash": profile_hash,
                        "enforcement": enforcement,
                        "audit": list(turn.events),
                    },
                )
            finally:
                enforcement["audit"] = (
                    "tool-policy-violation"
                    if isinstance(turn.error, CapabilityError)
                    else "tool-calls-observed"
                    if turn.tools_observed
                    else "no-tool-calls-observed"
                )
                try:
                    if request.on_checkpoint is not None:
                        request.on_checkpoint(
                            {"enforcement": enforcement, "audit": list(turn.events)}
                        )
                finally:
                    with self._lock:
                        self._turns.pop((thread_id, turn_id), None)

    def recover_turn(
        self, request: Any, *, thread_id: str, turn_id: str
    ) -> tuple[str, Any | None]:
        """Reconcile one durable native turn without dispatching model input."""
        deadline = (
            request.deadline
            if request.deadline is not None
            else time.monotonic() + request.timeout
        )

        def remaining(limit: float) -> float:
            value = min(limit, deadline - time.monotonic())
            if value <= 0:
                raise TimeoutError("Codex native recovery timed out")
            return value

        capabilities = self.probe(deadline=deadline)
        if "thread/read" not in capabilities.methods:
            return "unknown", None
        self._start(deadline=deadline)
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
        def read_turn(
            *, read_deadline: float = deadline
        ) -> tuple[Mapping[str, Any] | None, str | None]:
            rpc_deadline = min(deadline, read_deadline)
            timeout = min(10.0, rpc_deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError("Codex native recovery read timed out")
            result = self._rpc(
                "thread/read",
                {"threadId": thread_id, "includeTurns": True},
                timeout,
                deadline=rpc_deadline,
            )
            thread = result.get("thread")
            turns = thread.get("turns") if isinstance(thread, Mapping) else None
            if not isinstance(turns, list):
                return None, None
            match = next(
                (
                    turn
                    for turn in turns
                    if isinstance(turn, Mapping) and turn.get("id") == turn_id
                ),
                None,
            )
            status = match.get("status") if isinstance(match, Mapping) else None
            return match, status if isinstance(status, str) else None

        lock = self._thread_locks.setdefault(thread_id, threading.RLock())
        if not lock.acquire(timeout=remaining(request.timeout)):
            raise TimeoutError("Codex native recovery timed out waiting for its thread")
        cleanup_uncertain: str | None = None
        try:
            self._rpc(
                "thread/resume", common, remaining(10), deadline=deadline
            )
            self._thread_profiles.setdefault(thread_id, "")
            match, status = read_turn()
            if status in {"inProgress", "running", "pending"}:
                if not capabilities.supports_interrupt:
                    return "running", None
                # The interrupt is scoped to the recorded turn.  A failure can
                # be a completion race, so history remains authoritative.
                try:
                    self._rpc(
                        "turn/interrupt",
                        {"threadId": thread_id, "turnId": turn_id},
                        remaining(min(5.0, self.interrupt_grace_seconds)),
                        deadline=deadline,
                    )
                except (CodexProtocolError, TimeoutError):
                    pass
                reconcile_deadline = min(
                    deadline, time.monotonic() + self.interrupt_grace_seconds
                )
                while status in {"inProgress", "running", "pending"}:
                    if (
                        request.cancel_event is not None
                        and request.cancel_event.is_set()
                    ) or time.monotonic() >= reconcile_deadline:
                        break
                    try:
                        match, status = read_turn(read_deadline=reconcile_deadline)
                    except TimeoutError:
                        break
                    if status in {"inProgress", "running", "pending"}:
                        time.sleep(
                            max(
                                0.0,
                                min(0.05, reconcile_deadline - time.monotonic()),
                            )
                        )
            if status in {"failed", "interrupted", "cancelled"}:
                cleanup_methods = {
                    "thread/backgroundTerminals/clean",
                    "thread/backgroundTerminals/list",
                }
                if (
                    request.cancel_event is not None
                    and request.cancel_event.is_set()
                ):
                    cleanup_uncertain = (
                        "Codex background terminal cleanup was cancelled"
                    )
                elif not cleanup_methods.issubset(capabilities.methods):
                    cleanup_uncertain = (
                        "installed Codex cannot verify background terminal cleanup"
                    )
                else:
                    cleanup_deadline = min(
                        deadline, time.monotonic() + self.interrupt_grace_seconds
                    )

                    def cleanup_budget(limit: float) -> float:
                        value = min(limit, cleanup_deadline - time.monotonic())
                        if value <= 0:
                            raise TimeoutError(
                                "Codex background terminal cleanup timed out"
                            )
                        return value

                    try:
                        self._rpc(
                            "thread/backgroundTerminals/clean",
                            {"threadId": thread_id},
                            cleanup_budget(5.0),
                            deadline=cleanup_deadline,
                        )
                        while True:
                            cursor: str | None = None
                            found_background = False
                            while True:
                                params: dict[str, Any] = {
                                    "threadId": thread_id,
                                    "limit": 1000,
                                }
                                if cursor is not None:
                                    params["cursor"] = cursor
                                inventory = self._rpc(
                                    "thread/backgroundTerminals/list",
                                    params,
                                    cleanup_budget(5.0),
                                    deadline=cleanup_deadline,
                                )
                                data = inventory.get("data")
                                if not isinstance(data, list):
                                    raise CodexProtocolError(
                                        "Codex returned an invalid background terminal inventory"
                                    )
                                if data:
                                    found_background = True
                                    break
                                next_cursor = inventory.get("nextCursor")
                                if next_cursor is None or next_cursor == "":
                                    break
                                if not isinstance(next_cursor, str):
                                    raise CodexProtocolError(
                                        "Codex returned an invalid background terminal cursor"
                                    )
                                cursor = next_cursor
                            if not found_background:
                                break
                            if (
                                request.cancel_event is not None
                                and request.cancel_event.is_set()
                            ):
                                raise TimeoutError(
                                    "Codex background terminal cleanup was cancelled"
                                )
                            time.sleep(
                                max(
                                    0.0,
                                    min(
                                        0.05,
                                        cleanup_deadline - time.monotonic(),
                                    ),
                                )
                            )
                    except (CodexProtocolError, TimeoutError) as exc:
                        cleanup_uncertain = str(exc)
        except CodexProtocolError as exc:
            from .errors import SessionError

            raise SessionError(
                f"Codex thread {thread_id!r} could not be resumed: {exc}"
            ) from exc
        finally:
            lock.release()
        if match is None:
            return "unknown", None
        if status in {"inProgress", "running", "pending"}:
            return "running", None
        if status not in {"completed", "failed", "interrupted", "cancelled"}:
            return "unknown", None
        recovered = _Turn(thread_id, turn_id, request.tools, None)
        for item in match.get("items", ()):
            if isinstance(item, Mapping):
                self._record_event(
                    recovered,
                    "item/completed",
                    {"threadId": thread_id, "turnId": turn_id, "item": dict(item)},
                )
        checkpoint = request.checkpoint or {}
        enforcement = dict(checkpoint.get("enforcement") or {})
        enforcement["audit"] = (
            "tool-policy-violation"
            if isinstance(recovered.error, CapabilityError)
            else "tool-calls-observed"
            if recovered.tools_observed
            else "no-tool-calls-observed"
        )
        evidence = {"enforcement": enforcement, "audit": recovered.events}
        if cleanup_uncertain is not None:
            evidence["cleanup"] = {
                "status": "incomplete",
                "error": cleanup_uncertain,
            }
        if request.on_checkpoint is not None:
            request.on_checkpoint(evidence)
        if recovered.error is not None:
            raise recovered.error
        if status != "completed":
            if cleanup_uncertain is not None:
                return "unknown", None
            return "stopped", None
        if not recovered.messages:
            return "unknown", None
        from .providers import ProviderResponse

        return "completed", ProviderResponse(
            recovered.messages[-1],
            thread_id,
            {},
            {
                "provider": "codex",
                "codex_version": enforcement.get(
                    "codex_version", capabilities.version
                ),
                "thread_id": thread_id,
                "turn_id": turn_id,
                "recovered": True,
                **evidence,
            },
        )

    def interrupt(self, thread_id: str, turn_id: str) -> None:
        self._rpc(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            min(5.0, self.interrupt_grace_seconds),
        )

    def _stop_turn(self, turn: _Turn, reason: str) -> None:
        if self._process is not None and self._containment is not None:
            self._containment.capture_descendant_groups(self._process)
        cleanup_deadline = time.monotonic() + self.interrupt_grace_seconds
        try:
            self.interrupt(turn.thread_id, turn.turn_id)
        except Exception:  # noqa: BLE001,S110 - escalation below is authoritative
            pass
        # Codex deliberately keeps background terminals alive after interruption.
        # Give its native cleanup the grace period, including after turn/completed.
        self._kill_transport(
            CodexTurnError(reason),
            grace_seconds=0.1,
            cleanup_seconds=max(0.0, cleanup_deadline - time.monotonic()),
        )

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

    @staticmethod
    def _checkpoint_cleanup_failure(
        turns: Sequence[_Turn], error: BaseException
    ) -> list[BaseException]:
        checkpoint_errors: list[BaseException] = []
        for turn in turns:
            if turn.on_checkpoint is None:
                continue
            try:
                turn.on_checkpoint(
                    {
                        "cleanup": {
                            "status": "incomplete",
                            "error": str(error),
                        }
                    }
                )
            except BaseException as exc:
                checkpoint_errors.append(exc)
        return checkpoint_errors

    def _kill_transport(
        self,
        error: BaseException,
        *,
        grace_seconds: float = 0.1,
        cleanup_seconds: float = 0.1,
    ) -> None:
        process, containment = self._process, self._containment
        with self._lock:
            affected_turns = [turn for turn in self._turns.values() if not turn.completed]
        if process is not None and containment is not None:
            containment.capture_descendant_groups(process)
        if process is not None and process.poll() is None:
            deadline = time.monotonic() + cleanup_seconds
            if (
                self._capabilities is not None
                and "thread/backgroundTerminals/clean" in self._capabilities.methods
            ):
                with self._lock:
                    threads = set(self._thread_profiles) | {
                        thread_id for thread_id, _ in self._turns
                    }
                    requests = [
                        ("turn/interrupt", {"threadId": tid, "turnId": turn_id})
                        for (tid, turn_id), turn in self._turns.items()
                        if not turn.completed
                    ]
                requests.extend(
                    ("thread/backgroundTerminals/clean", {"threadId": thread_id})
                    for thread_id in sorted(threads)
                )
                for method, params in requests:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        self._rpc(method, params, remaining)
                    except Exception:  # noqa: BLE001,S110 - containment still closes below
                        pass
            # The cleanup RPC acknowledges acceptance before native jobs exit.
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(max(0.0, min(0.02, deadline - time.monotonic())))
            if containment is not None:
                containment.capture_descendant_groups(process)
        self._fail_transport(error)
        cleanup_errors: list[BaseException] = []
        if process is not None and containment is not None:
            if process.poll() is None:
                try:
                    containment.terminate(process, grace_seconds=grace_seconds)
                except BaseException as exc:  # cleanup still continues below
                    cleanup_errors.append(exc)
            try:
                containment.ensure_tree_exited(process, grace_seconds=grace_seconds)
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            failure = CodexProtocolError(
                "app-server process-tree cleanup was incomplete: "
                + "; ".join(str(exc) for exc in cleanup_errors)
            )
            checkpoint_errors = self._checkpoint_cleanup_failure(
                affected_turns, failure
            )
            if checkpoint_errors:
                failure = CodexProtocolError(
                    f"{failure}; cleanup checkpoint failed: "
                    + "; ".join(str(exc) for exc in checkpoint_errors)
                )
            self._fail_transport(failure)
            raise failure

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        cleanup_error: BaseException | None = None
        try:
            self._kill_transport(CodexProtocolError("Codex adapter closed"))
        except BaseException as exc:
            cleanup_error = exc
        process, containment = self._process, self._containment
        if process is not None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                if containment is not None:
                    try:
                        containment.terminate(process, grace_seconds=0.1)
                    except BaseException as exc:
                        cleanup_error = cleanup_error or exc
            if containment is not None:
                try:
                    containment.ensure_tree_exited(process, grace_seconds=0.1)
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc
        if containment is not None:
            containment.close()
        if cleanup_error is not None:
            raise cleanup_error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "CodexAppServerAdapter",
    "CodexProtocolError",
    "CodexTurnError",
]
