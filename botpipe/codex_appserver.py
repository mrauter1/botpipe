"""Pinned Codex app-server bridge for Botpipe-owned structured tools.

The adapter is selected explicitly with ``interface="app_server"``.  The pinned
upstream build still exposes ``update_plan`` and ``request_user_input``
unconditionally, so it cannot implement Botpipe's strictly tool-free generate
contract.  It can drive a source-audited, no-environment turn whose only
externally effectful calls are client-owned dynamic tools.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .native_tools import (
    ExactCommandTools,
    ReadOnlyTools,
    ToolObservation,
    command_scope_is_workspace_wide,
)
from .policy import OperationKind
from .processes import ProcessContainment
from .providers import (
    CapabilityError,
    CODEX_APPSERVER_CAPABILITIES,
    CodexProvider,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
    _CLIProvider,
    _NATIVE_EVENT_SINK,
    _atomic_json,
    _existing_response_or_raise,
    _now,
    _response_record,
    receipt_path,
)
from .recovery import RecoveryOutcome, Unknown
from .tool_evidence import ToolEvidence


PINNED_CODEX_VERSION = "0.131.0"
PINNED_CODEX_TAG = "rust-v0.131.0"
PINNED_CODEX_COMMIT = "05eb8678451435cbc8d79c6d8254276289f2bdf1"
TOOL_CALL_LIMIT = 16
TOOL_OUTPUT_BYTES = 32_000
_BOTPIPE_ROLE_PREFIX = (
    "Botpipe role update: earlier Botpipe role instructions are no longer active. "
    "Follow these role instructions until another Botpipe role update:\n\n"
)
_BOTPIPE_ROLE_RESET = (
    "Botpipe role update: earlier Botpipe role instructions are no longer active. "
    "No additional Botpipe role instructions apply; continue under the provider's "
    "base and developer instructions."
)

# This list is derived from codex-rs/core/src/tools/spec_plan.rs and
# codex-rs/tools/src/tool_config.rs at PINNED_CODEX_COMMIT.  Empty environments
# remove shell/apply-patch/view-image.  The feature overrides below close the
# conditional registrants.  These two non-effectful built-ins remain.
UNAVOIDABLE_INTERNAL_TOOLS = frozenset({"update_plan", "request_user_input"})
_RESERVED_NAMESPACES = frozenset(
    {
        "api_tool",
        "browser",
        "computer",
        "container",
        "file_search",
        "functions",
        "image_gen",
        "multi_tool_use",
        "python",
        "python_user_visible",
        "submodel_delegator",
        "terminal",
        "tool_search",
        "web",
    }
)


class CodexAppServerError(RuntimeError):
    """The pinned app-server contract could not be completed safely."""


class CodexAppServerCapabilityError(CodexAppServerError):
    """The installed build or requested profile is outside the audited set."""


class CodexAppServerProtocolError(CodexAppServerError):
    """The app-server emitted an invalid or unexpected protocol message."""


@dataclass(frozen=True, slots=True)
class DynamicTool:
    """One structured callback exposed through ``thread/start.dynamicTools``."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    namespace: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.name):
            raise ValueError("dynamic tool name must match [A-Za-z0-9_-]{1,64}")
        if self.namespace is not None and not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", self.namespace
        ):
            raise ValueError("dynamic tool namespace must match [A-Za-z0-9_-]{1,64}")
        if self.name == "mcp" or self.name.startswith("mcp__"):
            raise ValueError("dynamic tool name is reserved by the pinned protocol")
        if self.namespace is not None and (
            self.namespace == "mcp"
            or self.namespace.startswith("mcp__")
            or self.namespace in _RESERVED_NAMESPACES
        ):
            raise ValueError("dynamic tool namespace is reserved by the pinned protocol")
        if self.namespace is None and self.name in UNAVOIDABLE_INTERNAL_TOOLS:
            raise ValueError("dynamic tool name collides with a pinned native tool")
        if type(self.description) is not str or not self.description.strip():
            raise ValueError("dynamic tool description must be non-empty")
        schema = _plain_json(self.input_schema, label="dynamic tool input schema")
        if not isinstance(schema, dict):
            raise TypeError("dynamic tool input schema must be a JSON object")
        object.__setattr__(self, "input_schema", MappingProxyType(schema))

    @property
    def key(self) -> tuple[str | None, str]:
        return self.namespace, self.name

    def to_wire(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
            "deferLoading": False,
        }


@dataclass(frozen=True, slots=True)
class CodexAppServerSession:
    """Thread identity bound to the exact dynamic-tool registry."""

    thread_id: str
    tool_fingerprint: str


@dataclass(frozen=True, slots=True)
class CodexAppServerResult:
    text: str
    session: CodexAppServerSession
    turn_id: str
    usage: Mapping[str, Any] = field(default_factory=dict)
    events: tuple[Mapping[str, Any], ...] = ()


Mediator = Callable[[str, Mapping[str, Any]], object]
EventSink = Callable[[Mapping[str, Any]], None]


class EvidenceRecorder(Protocol):
    def prepare(self, envelopes: Any = ()) -> Path: ...
    def record(self, observation: Any) -> Path: ...


def tool_fingerprint(tools: Sequence[DynamicTool]) -> str:
    encoded = json.dumps(
        [tool.to_wire() for tool in tools],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _role_collaboration_mode(
    thread_response: Mapping[str, Any], instructions: str | None
) -> dict[str, Any]:
    model = thread_response.get("model")
    reasoning_effort = thread_response.get("reasoningEffort")
    if not isinstance(model, str) or not model:
        raise CodexAppServerProtocolError(
            "thread response contained no effective model"
        )
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise CodexAppServerProtocolError(
            "thread response contained an invalid reasoning effort"
        )
    role_instructions = (
        _BOTPIPE_ROLE_PREFIX + instructions
        if instructions
        else _BOTPIPE_ROLE_RESET
    )
    # Pinned core tests prove that changed collaboration instructions append a
    # developer delta while identical settings append nothing:
    # core/tests/suite/collaboration_instructions.rs (update + noop tests).
    return {
        "mode": "default",
        "settings": {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "developer_instructions": role_instructions,
        },
    }


def _plain_json(value: Any, *, label: str) -> Any:
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"{label} contains a non-finite number")
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{label} keys must be strings")
            result[key] = _plain_json(item, label=label)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain_json(item, label=label) for item in value]
    raise TypeError(f"{label} must contain plain JSON values")


def _clean_config_overrides() -> dict[str, Any]:
    """Return the audited conditional-tool closures for the pinned source."""
    disabled_features = (
        "shell_tool",
        "hooks",
        "code_mode",
        "code_mode_only",
        "exec_permission_approvals",
        "request_permissions_tool",
        "multi_agent",
        "multi_agent_v2",
        "enable_fanout",
        "apps",
        "enable_mcp_apps",
        "tool_search",
        "tool_suggest",
        "plugins",
        "plugin_hooks",
        "image_generation",
        "skill_mcp_dependency_install",
        "skill_env_var_dependency_prompt",
        "default_mode_request_user_input",
        "goals",
        "memories",
        "artifact",
    )
    result = {f"features.{name}": False for name in disabled_features}
    result.update(
        {
            "web_search": "disabled",
            "project_doc_max_bytes": 0,
            "include_permissions_instructions": False,
        }
    )
    return result


AUDITED_CONFIG_OVERRIDES = MappingProxyType(_clean_config_overrides())


class _JsonlProcess:
    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        max_message_bytes: int,
        max_messages: int,
        max_stderr_bytes: int = 65_536,
    ) -> None:
        self.containment = ProcessContainment.create()
        try:
            self.process = subprocess.Popen(
                tuple(command),
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                **self.containment.creation_kwargs,
            )
        except BaseException:
            self.containment.close()
            raise
        try:
            self.containment.attach_and_start(self.process)
        except BaseException:
            # Assignment failure leaves a Windows child suspended and POSIX
            # registration failure leaves no verified group safe to signal.
            # Killing the known leader is the only safe fallback in either case.
            try:
                self.process.kill()
                self.process.wait(timeout=2)
            finally:
                self.containment.close()
            raise
        self.max_message_bytes = max_message_bytes
        self.messages: queue.Queue[Mapping[str, Any] | BaseException | None] = (
            queue.Queue(maxsize=max(1, min(max_messages, 64)))
        )
        self.max_stderr_bytes = max_stderr_bytes
        self.stderr = bytearray()
        self.stderr_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.close_error: BaseException | None = None
        self.closed = False
        self.stopping = threading.Event()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _enqueue(self, message: Mapping[str, Any] | BaseException | None) -> None:
        while not self.stopping.is_set():
            try:
                self.messages.put(message, timeout=0.1)
                return
            except queue.Full:
                continue

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        try:
            while True:
                line = self.process.stdout.readline(self.max_message_bytes + 1)
                if not line:
                    break
                if len(line) > self.max_message_bytes:
                    raise CodexAppServerProtocolError(
                        "app-server JSONL line exceeds protocol byte limit"
                    )
                if not line.strip():
                    continue
                try:
                    decoded = line.decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise CodexAppServerProtocolError(
                        "app-server JSONL was not valid UTF-8"
                    ) from exc
                value = json.loads(decoded)
                if not isinstance(value, Mapping):
                    raise CodexAppServerProtocolError(
                        "app-server JSONL messages must be objects"
                    )
                self._enqueue(dict(value))
        except BaseException as exc:
            self._enqueue(exc)
        finally:
            self._enqueue(None)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        while not self.stopping.is_set():
            chunk = self.process.stderr.read(4096)
            if not chunk:
                return
            with self.stderr_lock:
                self.stderr.extend(chunk)
                excess = len(self.stderr) - self.max_stderr_bytes
                if excess > 0:
                    del self.stderr[:excess]

    def _stderr_text(self) -> str:
        with self.stderr_lock:
            captured = bytes(self.stderr)
        return captured.decode("utf-8", errors="replace").strip()

    def send(self, message: Mapping[str, Any]) -> None:
        assert self.process.stdin is not None
        encoded = json.dumps(
            message, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        with self.write_lock:
            self.process.stdin.write(encoded + b"\n")
            self.process.stdin.flush()

    def receive(self, deadline: float) -> Mapping[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Codex app-server deadline expired")
        while True:
            try:
                message = self.messages.get(timeout=min(remaining, 0.1))
                break
            except queue.Empty as exc:
                if self.process.poll() is not None or self.stopping.is_set():
                    detail = self._stderr_text()
                    raise CodexAppServerProtocolError(
                        "app-server closed before terminal result"
                        + (f": {detail}" if detail else "")
                    ) from exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Codex app-server deadline expired") from exc
        if isinstance(message, BaseException):
            raise CodexAppServerProtocolError(
                f"invalid app-server JSONL: {message}"
            ) from message
        if message is None:
            detail = self._stderr_text()
            raise CodexAppServerProtocolError(
                f"app-server closed before terminal result{': ' + detail if detail else ''}"
            )
        return message

    def close(self) -> None:
        with self.close_lock:
            if self.closed:
                if self.close_error is not None:
                    raise RuntimeError(
                        "app-server process-tree cleanup was not confirmed"
                    ) from self.close_error
                return
            self.stopping.set()
            cleanup_error: BaseException | None = None
            try:
                # The leader may already have exited after reporting a terminal
                # turn.  Containment still has to prove that its descendants
                # cannot outlive the successful response.
                self.containment.ensure_tree_exited(
                    self.process, grace_seconds=0.1
                )
            except BaseException as exc:
                cleanup_error = exc
            finally:
                for stream in (
                    self.process.stdin,
                    self.process.stdout,
                    self.process.stderr,
                ):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError:
                            pass
                try:
                    self.containment.close()
                except BaseException as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
                self.closed = True
                self.close_error = cleanup_error
            if cleanup_error is not None:
                raise cleanup_error


class CodexAppServerBridge:
    """Bidirectional client for the pinned experimental dynamic-tool protocol."""

    def __init__(
        self,
        *,
        command: Sequence[str] = ("codex", "app-server", "--listen", "stdio://"),
        version_command: Sequence[str] = ("codex", "--version"),
        codex_home: Path,
        env: Mapping[str, str] | None = None,
        version_probe: Callable[[], str] | None = None,
        max_event_bytes: int = 1_000_000,
        max_total_event_bytes: int = 8_000_000,
        max_events: int = 10_000,
    ) -> None:
        if (
            not command
            or not version_command
            or isinstance(command, (str, bytes))
            or isinstance(version_command, (str, bytes))
        ):
            raise ValueError("Codex commands must be non-empty argv sequences")
        if max_event_bytes < 1 or max_total_event_bytes < 1 or max_events < 1:
            raise ValueError("Codex evidence limits must be positive")
        self.command = tuple(command)
        self.version_command = tuple(version_command)
        self.codex_home = Path(codex_home).resolve()
        self.env = dict(env or {})
        self.version_probe = version_probe
        self.max_event_bytes = max_event_bytes
        self.max_total_event_bytes = max_total_event_bytes
        self.max_events = max_events
        self._active_lock = threading.Lock()
        self._active: dict[str, _Conversation] = {}

    def preflight(self, workspace: Path) -> None:
        """Validate all locally knowable constraints before budget dispatch."""
        self.verify_installation()
        self._verify_project_config(Path(workspace).resolve(strict=True))

    def interrupt(self, owner_id: str, *, timeout: float = 2.0) -> str | None:
        """Attempt native interruption for an active turn, then contain it."""
        with self._active_lock:
            state = self._active.get(owner_id)
        if state is None:
            return None
        requested = False
        if state.thread_id is not None and state.turn_id is not None:
            try:
                state.send_rpc_no_wait(
                    "turn/interrupt",
                    {"threadId": state.thread_id, "turnId": state.turn_id},
                )
                requested = True
            except (OSError, ValueError):
                pass
            state.terminal_event.wait(max(0.0, float(timeout)))
        state.process.close()
        return "turn-interrupt" if requested else "contained"

    def verify_installation(self) -> None:
        """Fail before app-server dispatch on version or config-surface drift."""
        version_text = (
            self.version_probe()
            if self.version_probe is not None
            else subprocess.run(
                self.version_command,
                check=True,
                text=True,
                capture_output=True,
                timeout=10,
                env={**os.environ, **self.env},
            ).stdout.strip()
        )
        match = re.search(r"(?:codex-cli\s+)?([0-9]+\.[0-9]+\.[0-9]+)$", version_text.strip())
        if match is None or match.group(1) != PINNED_CODEX_VERSION:
            raise CodexAppServerCapabilityError(
                f"Codex mediated profile requires codex-cli {PINNED_CODEX_VERSION} "
                f"from {PINNED_CODEX_TAG} ({PINNED_CODEX_COMMIT}); found {version_text!r}"
            )
        self._verify_config_hygiene()

    def _verify_config_hygiene(self) -> None:
        # A private home may contain auth and model cache, but none of the
        # surfaces that can register tools or spawn lifecycle hooks.
        prohibited = (
            self.codex_home / "config.toml",
            self.codex_home / "hooks.json",
            self.codex_home / "skills",
            self.codex_home / "plugins",
        )
        present = [str(path) for path in prohibited if path.exists()]
        system = Path("/etc/codex/config.toml")
        if system.exists():
            present.append(str(system))
        if present:
            raise CodexAppServerCapabilityError(
                "Codex mediated profile requires an isolated configuration home; "
                "prohibited configuration surfaces exist: " + ", ".join(present)
            )

    def execute(
        self,
        *,
        prompt: str,
        workspace: Path,
        tools: Sequence[DynamicTool],
        mediator: Mediator,
        timeout: float,
        instructions: str | None = None,
        model: str | None = None,
        output_schema: Mapping[str, Any] | None = None,
        session: CodexAppServerSession | None = None,
        event_sink: EventSink | None = None,
        evidence: EvidenceRecorder | None = None,
        envelopes: Any = (),
        registry_fingerprint: str | None = None,
        owner_id: str | None = None,
    ) -> CodexAppServerResult:
        """Run one constrained turn, servicing only registered dynamic tools.

        At least one dynamic tool is required.  The pinned source cannot hide
        its two internal tools and therefore cannot implement tool-free
        generation.  Callers must keep this bridge out of that operation.
        """
        self._validate_execute(
            prompt, workspace, tools, mediator, timeout, output_schema, session
        )
        if owner_id is not None and not owner_id:
            raise ValueError("owner_id must be non-empty when provided")
        root = Path(workspace).resolve(strict=True)
        self.preflight(root)
        fingerprint = registry_fingerprint or tool_fingerprint(tools)
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("registry fingerprint must be a lowercase SHA-256 digest")
        if session is not None and session.tool_fingerprint != fingerprint:
            raise CodexAppServerCapabilityError(
                "resumed Codex thread is bound to a different dynamic-tool registry"
            )
        if evidence is not None:
            # The manifest must be durable before any native model process can
            # see the tool registry.
            evidence.prepare(envelopes)

        environment = {
            **os.environ,
            **self.env,
            "CODEX_HOME": str(self.codex_home),
            "RUST_LOG": "error",
            "LOG_FORMAT": "json",
        }
        process = _JsonlProcess(
            self.command,
            cwd=root,
            env=environment,
            max_message_bytes=self.max_event_bytes,
            max_messages=self.max_events,
        )
        deadline = time.monotonic() + float(timeout)
        state = _Conversation(
            process=process,
            deadline=deadline,
            tools={tool.key: tool for tool in tools},
            mediator=mediator,
            event_sink=event_sink,
            max_event_bytes=self.max_event_bytes,
            max_total_event_bytes=self.max_total_event_bytes,
            max_events=self.max_events,
            evidence=evidence,
        )
        if owner_id is not None:
            with self._active_lock:
                if owner_id in self._active:
                    process.close()
                    raise CodexAppServerCapabilityError(
                        f"Codex app-server owner {owner_id!r} is already active"
                    )
                self._active[owner_id] = state
        try:
            state.rpc(
                "initialize",
                {
                    "clientInfo": {
                        "name": "botpipe",
                        "title": "Botpipe",
                        "version": "1",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            process.send({"method": "initialized"})
            self._audit_runtime_config(
                state.rpc(
                    "config/read", {"includeLayers": True, "cwd": str(root)}
                ),
                state.rpc("configRequirements/read", None),
            )
            if session is None:
                params: dict[str, Any] = {
                    "cwd": str(root),
                    "model": model,
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "ephemeral": False,
                    "environments": [],
                    "dynamicTools": [tool.to_wire() for tool in tools],
                    "config": dict(AUDITED_CONFIG_OVERRIDES),
                }
                started = state.rpc(
                    "thread/start",
                    {key: value for key, value in params.items() if value is not None},
                )
                thread_response = started
                thread = started.get("thread")
                thread_id = thread.get("id") if isinstance(thread, Mapping) else None
            else:
                resumed = state.rpc(
                    "thread/resume",
                    {
                        "threadId": session.thread_id,
                        "cwd": str(root),
                        "approvalPolicy": "never",
                        "sandbox": "read-only",
                        "config": dict(AUDITED_CONFIG_OVERRIDES),
                    },
                )
                thread_response = resumed
                thread = resumed.get("thread")
                thread_id = thread.get("id") if isinstance(thread, Mapping) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexAppServerProtocolError("thread response contained no thread id")
            collaboration_mode = (
                _role_collaboration_mode(thread_response, instructions)
                if session is not None or instructions
                else None
            )
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "environments": [],
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                "collaborationMode": collaboration_mode,
                "outputSchema": (
                    _plain_json(output_schema, label="output schema")
                    if output_schema is not None
                    else None
                ),
            }
            turn_started = state.rpc(
                "turn/start",
                {key: value for key, value in turn_params.items() if value is not None},
            )
            turn = turn_started.get("turn")
            turn_id = turn.get("id") if isinstance(turn, Mapping) else None
            if not isinstance(turn_id, str) or not turn_id:
                raise CodexAppServerProtocolError("turn/start contained no turn id")
            state.thread_id = thread_id
            state.turn_id = turn_id
            text, usage = state.wait_for_terminal()
            return CodexAppServerResult(
                text=text,
                session=CodexAppServerSession(thread_id, fingerprint),
                turn_id=turn_id,
                usage=MappingProxyType(usage),
                events=tuple(MappingProxyType(dict(event)) for event in state.events),
            )
        except TimeoutError:
            if state.thread_id and state.turn_id:
                try:
                    state.send_rpc_no_wait(
                        "turn/interrupt",
                        {"threadId": state.thread_id, "turnId": state.turn_id},
                    )
                except Exception:
                    pass
            raise
        finally:
            state.terminal_event.set()
            if owner_id is not None:
                with self._active_lock:
                    if self._active.get(owner_id) is state:
                        del self._active[owner_id]
            process.close()

    def _validate_execute(
        self,
        prompt: str,
        workspace: Path,
        tools: Sequence[DynamicTool],
        mediator: Mediator,
        timeout: float,
        output_schema: Mapping[str, Any] | None,
        session: CodexAppServerSession | None,
    ) -> None:
        if type(prompt) is not str or not prompt:
            raise ValueError("prompt must be non-empty")
        if not tools:
            raise CodexAppServerCapabilityError(
                "pinned Codex app-server cannot hide update_plan and request_user_input; "
                "tool-free generate is unsupported"
            )
        keys = [tool.key for tool in tools]
        if len(keys) != len(set(keys)):
            raise ValueError("dynamic tool names must be unique within each namespace")
        if not callable(mediator):
            raise TypeError("mediator must be callable")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
            or not math.isfinite(float(timeout))
        ):
            raise ValueError("timeout must be greater than zero")
        if output_schema is not None:
            _plain_json(output_schema, label="output schema")
        if session is not None and not session.thread_id:
            raise ValueError("session thread id must be non-empty")
        Path(workspace).resolve(strict=True)

    @staticmethod
    def _verify_project_config(workspace: Path) -> None:
        for root in (workspace, *workspace.parents):
            for relative in (Path(".codex/config.toml"), Path(".codex/hooks.json")):
                candidate = root / relative
                if candidate.exists():
                    raise CodexAppServerCapabilityError(
                        f"workspace-scoped Codex configuration is unavailable to the "
                        f"mediated profile: {candidate}"
                    )

    @staticmethod
    def _audit_runtime_config(
        config_read: Mapping[str, Any], requirements_read: Mapping[str, Any]
    ) -> None:
        """Reject hidden registries and managed overrides before thread dispatch."""
        if requirements_read.get("requirements") is not None:
            # The public projection omits some managed MCP/plugin constraints,
            # so the only complete fail-closed assertion is no requirements.
            raise CodexAppServerCapabilityError(
                "managed Codex requirements cannot be proven compatible with the "
                "pinned mediated inventory"
            )
        forbidden = {"mcp_servers", "plugins", "hooks", "notify", "skills"}
        documents: list[Mapping[str, Any]] = []
        config = config_read.get("config")
        if isinstance(config, Mapping):
            documents.append(config)
        layers = config_read.get("layers")
        if not isinstance(layers, list):
            raise CodexAppServerProtocolError(
                "config/read did not return the requested configuration layers"
            )
        for layer in layers:
            if isinstance(layer, Mapping) and isinstance(layer.get("config"), Mapping):
                documents.append(layer["config"])
        surfaced = sorted(
            key
            for document in documents
            for key in forbidden.intersection(document)
            if document.get(key) not in (None, {}, [])
        )
        if surfaced:
            raise CodexAppServerCapabilityError(
                "Codex configuration contains unaudited tool or hook surfaces: "
                + ", ".join(dict.fromkeys(surfaced))
            )


@dataclass(slots=True)
class _Conversation:
    process: _JsonlProcess
    deadline: float
    tools: Mapping[tuple[str | None, str], DynamicTool]
    mediator: Mediator
    event_sink: EventSink | None
    max_event_bytes: int
    max_total_event_bytes: int
    max_events: int
    evidence: EvidenceRecorder | None = None
    next_id: int = 1
    thread_id: str | None = None
    turn_id: str | None = None
    events: list[Mapping[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    rejected_request: str | None = None
    seen_call_ids: set[str] = field(default_factory=set)
    id_lock: threading.Lock = field(default_factory=threading.Lock)
    terminal_event: threading.Event = field(default_factory=threading.Event)
    retained_event_bytes: int = 0

    def _next_request_id(self) -> int:
        with self.id_lock:
            request_id = self.next_id
            self.next_id += 1
        return request_id

    def rpc(
        self, method: str, params: Mapping[str, Any] | None
    ) -> Mapping[str, Any]:
        request_id = self._next_request_id()
        request: dict[str, Any] = {"method": method, "id": request_id}
        if params is not None:
            request["params"] = dict(params)
        self.process.send(request)
        while True:
            message = self.process.receive(self.deadline)
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise CodexAppServerProtocolError(
                        f"{method} failed: {message['error']!r}"
                    )
                result = message.get("result")
                if not isinstance(result, Mapping):
                    raise CodexAppServerProtocolError(
                        f"{method} response result must be an object"
                    )
                return dict(result)
            self.handle(message)

    def send_rpc_no_wait(self, method: str, params: Mapping[str, Any]) -> None:
        request_id = self._next_request_id()
        self.process.send({"method": method, "id": request_id, "params": dict(params)})

    def handle(self, message: Mapping[str, Any]) -> None:
        encoded = json.dumps(message, allow_nan=False, separators=(",", ":")).encode()
        if len(encoded) > self.max_event_bytes:
            raise CodexAppServerProtocolError("app-server event exceeds evidence limit")
        if self.retained_event_bytes + len(encoded) > self.max_total_event_bytes:
            raise CodexAppServerProtocolError(
                "app-server cumulative event evidence exceeds byte limit"
            )
        if len(self.events) >= self.max_events:
            raise CodexAppServerProtocolError("app-server event count exceeds evidence limit")
        event = dict(message)
        self.events.append(event)
        self.retained_event_bytes += len(encoded)
        if self.event_sink is not None:
            self.event_sink(MappingProxyType(event))
        method = message.get("method")
        if "id" in message and isinstance(method, str):
            self._server_request(message)
            return
        if not isinstance(method, str):
            return
        params = message.get("params")
        if not isinstance(params, Mapping):
            return
        if method == "item/completed":
            item = params.get("item")
            if isinstance(item, Mapping):
                item_type = item.get("type")
                if item_type == "agentMessage" and isinstance(item.get("text"), str):
                    self.messages.append(item["text"])
                self._reject_effectful_item(item_type)
        elif method == "item/started":
            item = params.get("item")
            if isinstance(item, Mapping):
                self._reject_effectful_item(item.get("type"))
        elif method == "thread/tokenUsage/updated":
            token_usage = params.get("tokenUsage")
            if isinstance(token_usage, Mapping):
                self.usage = _plain_json(token_usage, label="token usage")
        elif method == "turn/completed":
            turn = params.get("turn")
            if isinstance(turn, Mapping) and turn.get("id") == self.turn_id:
                self.terminal_event.set()

    def _reject_effectful_item(self, item_type: Any) -> None:
        allowed = {
            "userMessage",
            "agentMessage",
            "reasoning",
            "plan",
            "dynamicToolCall",
            "enteredReviewMode",
            "exitedReviewMode",
        }
        if isinstance(item_type, str) and item_type not in allowed:
            raise CodexAppServerProtocolError(
                f"unaudited native tool item appeared in constrained turn: {item_type}"
            )

    def _server_request(self, message: Mapping[str, Any]) -> None:
        request_id = message["id"]
        method = message.get("method")
        if method != "item/tool/call":
            self.process.send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Botpipe rejects non-mediated server requests",
                    },
                }
            )
            self.rejected_request = str(method)
            return
        params = message.get("params")
        if not isinstance(params, Mapping):
            raise CodexAppServerProtocolError("dynamic tool call params must be an object")
        if params.get("threadId") != self.thread_id or params.get("turnId") != self.turn_id:
            raise CodexAppServerProtocolError(
                "dynamic tool call did not match the active thread and turn"
            )
        call_id = params.get("callId")
        if not isinstance(call_id, str) or not call_id:
            raise CodexAppServerProtocolError("dynamic tool call contained no call id")
        if call_id in self.seen_call_ids:
            raise CodexAppServerProtocolError("duplicate dynamic tool call id")
        self.seen_call_ids.add(call_id)
        key = params.get("namespace"), params.get("tool")
        if key not in self.tools:
            self.process.send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "unknown mediated tool"},
                }
            )
            self.rejected_request = f"item/tool/call:{key!r}"
            return
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            raise CodexAppServerProtocolError("dynamic tool arguments must be an object")
        result = self.mediator(self.tools[key].name, MappingProxyType(dict(arguments)))
        if hasattr(result, "to_record") and callable(result.to_record):
            if self.evidence is None:
                raise CodexAppServerProtocolError(
                    "structured tool observations require durable evidence"
                )
            # Persist before returning any part of the result to the model.
            self.evidence.record(result)
            result = result.to_record()
        if isinstance(result, str):
            text = result
            success = True
        elif isinstance(result, Mapping):
            plain = _plain_json(result, label="mediator result")
            text = json.dumps(plain, ensure_ascii=False, separators=(",", ":"))
            success = True
        else:
            raise TypeError("mediator must return a string or plain JSON mapping")
        if len(text.encode()) > self.max_event_bytes:
            raise CodexAppServerProtocolError("mediator result exceeds evidence limit")
        self.process.send(
            {
                "id": request_id,
                "result": {
                    "contentItems": [{"type": "inputText", "text": text}],
                    "success": success,
                },
            }
        )

    def wait_for_terminal(self) -> tuple[str, dict[str, Any]]:
        while True:
            message = self.process.receive(self.deadline)
            self.handle(message)
            if message.get("method") != "turn/completed":
                continue
            params = message.get("params")
            turn = params.get("turn") if isinstance(params, Mapping) else None
            if not isinstance(turn, Mapping):
                raise CodexAppServerProtocolError("turn/completed contained no turn")
            if turn.get("id") != self.turn_id:
                continue
            status = turn.get("status")
            if status != "completed":
                raise CodexAppServerProtocolError(
                    f"Codex turn ended with non-success status {status!r}"
                )
            if self.rejected_request is not None:
                raise CodexAppServerProtocolError(
                    "model attempted an unavailable native interaction: "
                    + self.rejected_request
                )
            if not self.messages:
                raise CodexAppServerProtocolError(
                    "Codex turn completed without an agent message"
                )
            return self.messages[-1], dict(self.usage)


def _session_binding_path(receipt_dir: Path, thread_id: str) -> Path:
    identity = hashlib.sha256(thread_id.encode()).hexdigest()
    return Path(receipt_dir) / "codex-app-server-sessions" / f"{identity}.json"


def _profile_fingerprint(
    tools: Sequence[DynamicTool],
    envelopes: Mapping[str, Any] | Sequence[Any],
    *,
    read_roots: Sequence[Path] = (),
    read_exclusions: Sequence[Path] = (),
) -> str:
    values = envelopes.values() if isinstance(envelopes, Mapping) else envelopes
    envelope_records = [
        item.to_record() if hasattr(item, "to_record") else dict(item)
        for item in values
    ]
    envelope_records.sort(
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
    )
    record = {
        "adapter": CODEX_APPSERVER_CAPABILITIES.version,
        "source_commit": PINNED_CODEX_COMMIT,
        "tools": [tool.to_wire() for tool in tools],
        "envelopes": envelope_records,
        "read_roots": [str(path.resolve()) for path in read_roots],
        "read_exclusions": [str(path.resolve()) for path in read_exclusions],
    }
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class CodexAppServerProvider(_CLIProvider):
    """Real ProviderAdapter wrapper for mediated app-server turns.

    ``generate`` is accepted only with non-empty exact command grants. Query
    exposes bounded read/list/search tools plus one fixed read-only git-status
    recipe. Effectful run delegates to :class:`CodexProvider`.
    """

    name = "codex"
    capabilities = CODEX_APPSERVER_CAPABILITIES
    supported_settings: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        codex_home: str | Path | None = None,
        app_server_command: Sequence[str] = (
            "codex",
            "app-server",
            "--listen",
            "stdio://",
        ),
        version_command: Sequence[str] = ("codex", "--version"),
        run_command: str | Sequence[str] = ("codex", "exec"),
        env: Mapping[str, str] | None = None,
        bridge: CodexAppServerBridge | None = None,
    ) -> None:
        super().__init__(("codex-app-server",), env=env)
        if bridge is None:
            selected_home = codex_home or (env or {}).get("BOTPIPE_CODEX_HOME")
            if selected_home is None:
                raise ValueError(
                    "Codex app-server profile requires an isolated codex_home "
                    "containing credentials but no config/tool registries"
                )
            bridge = CodexAppServerBridge(
                command=app_server_command,
                version_command=version_command,
                codex_home=Path(selected_home),
                env=env,
            )
        elif codex_home is not None:
            raise ValueError("codex_home cannot be combined with an injected bridge")
        self.bridge = bridge
        self._run_adapter = CodexProvider(run_command, env=env)

    def validate_request(self, request: ProviderRequest) -> None:
        super().validate_request(request)
        if request.operation is OperationKind.RUN:
            self._run_adapter.validate_request(request)
            return
        if request.operation is OperationKind.GENERATE and not request.allow_commands:
            raise CapabilityError(
                "pinned Codex app-server cannot enforce strict tool-free generate; "
                "provide an exact command grant or select another provider"
            )
        if request.operation is OperationKind.GENERATE:
            policy = request.policy.effective()
            if not command_scope_is_workspace_wide(
                request.workspace, policy.allow_read, policy.deny_read
            ):
                raise CapabilityError(
                    "Codex exact-command generation requires one workspace-wide "
                    "read root and no deny_read entries"
                )
        # Version and ambient home checks occur before any receipt or native
        # planning process. Effective config layers are audited by the protocol
        # bridge before thread/start.
        self.bridge.preflight(request.workspace)

    def cancel(self, operation_id: str) -> RecoveryOutcome:
        attempted = self.bridge.interrupt(operation_id, timeout=2.0)
        if attempted is not None:
            detail = (
                "native turn/interrupt was requested and the owned process was bounded"
                if attempted == "turn-interrupt"
                else "the owned pre-turn app-server process was bounded"
            )
            return Unknown(
                f"Codex app-server attempt {operation_id!r}: {detail}; terminal "
                "quiescence was not independently acknowledged"
            )
        delegated = self._run_adapter.cancel(operation_id)
        if not isinstance(delegated, Unknown):
            return delegated
        return Unknown(
            f"Codex app-server attempt {operation_id!r}: no owned active app-server "
            "process was found; terminal quiescence was not independently acknowledged"
        )

    def run(self, request: ProviderRequest) -> ProviderResponse:
        self.validate_request(request)
        if request.operation is OperationKind.RUN:
            return self._run_adapter.run(request)
        existing = _existing_response_or_raise(request)
        if existing is not None:
            return existing
        prior = self._reconcile_prior_attempts(request)
        if prior is not None:
            return prior

        tools: list[DynamicTool]
        observations: list[ToolObservation] = []
        cleanups: list[Callable[[], None]] = []
        evidence = ToolEvidence(
            request,
            self.capabilities.version,
            max_observations=TOOL_CALL_LIMIT,
            max_bytes=1_000_000,
        )
        try:
            tools, mediator, envelopes, roots, exclusions = self._mediator(
                request, observations, cleanups
            )
            fingerprint = _profile_fingerprint(
                tools,
                envelopes,
                read_roots=roots,
                read_exclusions=exclusions,
            )
            session = self._load_session(request, fingerprint)
            evidence.prepare(envelopes)
        except BaseException:
            for cleanup in cleanups:
                cleanup()
            raise

        from .dispatches import Dispatch

        try:
            dispatch = Dispatch(self, request)
        except BaseException:
            for cleanup in cleanups:
                cleanup()
            raise
        path = receipt_path(request)
        started = {
            "version": 1,
            "provider": self.name,
            "adapter_version": self.capabilities.version,
            "source_commit": PINNED_CODEX_COMMIT,
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "operation": request.operation.value,
            "tool_fingerprint": fingerprint,
            "status": "prepared",
            "prepared_at": _now(),
        }
        dispatched = False
        try:
            _atomic_json(path, started)
            started.update(status="dispatched", dispatched_at=_now())
            _atomic_json(path, started)
            dispatched = True
            dispatch.started()
            policy = request.policy.effective()
            result = self.bridge.execute(
                prompt=request.prompt,
                workspace=request.workspace,
                tools=tools,
                mediator=mediator,
                timeout=dispatch.timeout,
                instructions=request.instructions,
                model=policy.model,
                output_schema=request.output_schema,
                session=session,
                event_sink=_NATIVE_EVENT_SINK.get(),
                evidence=evidence,
                envelopes=envelopes,
                registry_fingerprint=fingerprint,
                owner_id=request.operation_id,
            )
            usage = self._usage(result.usage)
            response = ProviderResponse(
                result.text,
                result.session.thread_id,
                usage,
                {
                    "provider": self.name,
                    "adapter_version": self.capabilities.version,
                    "source_commit": PINNED_CODEX_COMMIT,
                    "tool_fingerprint": fingerprint,
                    "tool_observations": [item.to_record() for item in observations],
                },
            )
            self._save_session(request, result.session)
            completed = {
                **started,
                "status": "completed",
                "finished_at": _now(),
                "session_id": result.session.thread_id,
                "turn_id": result.turn_id,
                "response": _response_record(response),
            }
            _atomic_json(path, completed)
        except (KeyboardInterrupt, SystemExit):
            dispatch.finish("interrupted")
            raise
        except BaseException as exc:
            if dispatched:
                uncertain = {
                    **started,
                    "status": "uncertain",
                    "finished_at": _now(),
                    "error": f"Codex app-server terminal result was not committed: {exc}",
                }
                _atomic_json(path, uncertain)
                dispatch.finish("failed", error=exc)
                raise ProviderInterruptedError(
                    uncertain["error"], receipt=path
                ) from exc
            dispatch.finish("failed", error=exc)
            raise
        finally:
            for cleanup in cleanups:
                cleanup()
        dispatch.finish("completed", usage=response.usage)
        return response

    def _mediator(
        self,
        request: ProviderRequest,
        observations: list[ToolObservation],
        cleanups: list[Callable[[], None]],
    ) -> tuple[
        list[DynamicTool],
        Mediator,
        Mapping[str, Any],
        tuple[Path, ...],
        tuple[Path, ...],
    ]:
        policy = request.policy.effective()
        roots = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.allow_read or ())
        )
        exclusions = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.deny_read or ())
        )
        reads: ReadOnlyTools | None = None
        if request.operation is OperationKind.QUERY:
            reads = ReadOnlyTools(
                roots,
                exclusions=exclusions,
                max_output_bytes=TOOL_OUTPUT_BYTES,
                read_fence=request.read_fence,
            )
            cleanups.append(reads.close)
            commands = None
            envelopes = reads.command_envelopes
            tools = self._query_tools()
        else:
            commands = ExactCommandTools(
                request.workspace,
                request.allow_commands,
                max_output_bytes=TOOL_OUTPUT_BYTES,
            )
            tools = [
                DynamicTool(
                    "exec_grant",
                    "Execute one explicitly authorized read-only command envelope.",
                    {
                        "type": "object",
                        "properties": {
                            "grant_id": {
                                "type": "string",
                                "enum": list(commands.envelopes),
                            }
                        },
                        "required": ["grant_id"],
                        "additionalProperties": False,
                    },
                    namespace="botpipe",
                )
            ]
            envelopes = commands.envelopes
            cleanups.append(commands.close)

        def mediate(name: str, arguments: Mapping[str, Any]) -> ToolObservation:
            if len(observations) >= TOOL_CALL_LIMIT:
                raise CapabilityError(
                    f"native tool call limit of {TOOL_CALL_LIMIT} was reached"
                )
            if name == "exec_grant" and request.operation is OperationKind.GENERATE:
                self._exact_keys(arguments, {"grant_id"})
                observation = commands.execute(arguments.get("grant_id"))
            elif name == "read" and reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = reads.read(arguments.get("path"))
            elif name == "list" and reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = reads.list(arguments.get("path", "."))
            elif name == "search" and reads is not None:
                self._exact_keys(arguments, {"query", "path"})
                observation = reads.search(
                    arguments.get("query"), arguments.get("path", ".")
                )
            elif name == "count_lines" and reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = reads.count_lines(arguments.get("path"))
            else:
                raise CapabilityError(f"Codex requested unavailable tool {name!r}")
            observations.append(observation)
            return observation

        return tools, mediate, envelopes, roots, exclusions

    @staticmethod
    def _query_tools() -> list[DynamicTool]:
        tools = [
            DynamicTool(
                "read",
                "Read an authorized non-private file.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                namespace="botpipe",
            ),
            DynamicTool(
                "list",
                "List an authorized directory.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "additionalProperties": False,
                },
                namespace="botpipe",
            ),
            DynamicTool(
                "search",
                "Search authorized files for a literal string.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                namespace="botpipe",
            ),
        ]
        tools.append(
            DynamicTool(
                "count_lines",
                "Count lines in one authorized file using a fixed native command.",
                {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                    "additionalProperties": False,
                },
                namespace="botpipe",
            )
        )
        return tools

    @staticmethod
    def _exact_keys(value: Mapping[str, Any], allowed: set[str]) -> None:
        unknown = set(value) - allowed
        if unknown:
            raise CapabilityError(
                "Codex dynamic tool call contains unsupported fields: "
                + ", ".join(sorted(map(str, unknown)))
            )

    @staticmethod
    def _usage(value: Mapping[str, Any]) -> dict[str, Any]:
        last = value.get("last")
        if not isinstance(last, Mapping):
            last = value.get("total")
        if not isinstance(last, Mapping):
            return {}
        aliases = {
            "input_tokens": "inputTokens",
            "cached_input_tokens": "cachedInputTokens",
            "output_tokens": "outputTokens",
            "reasoning_tokens": "reasoningOutputTokens",
            "total_tokens": "totalTokens",
        }
        return {
            target: last[source]
            for target, source in aliases.items()
            if isinstance(last.get(source), int) and not isinstance(last[source], bool)
        }

    def _load_session(
        self, request: ProviderRequest, fingerprint: str
    ) -> CodexAppServerSession | None:
        if request.session_id is None:
            return None
        path = _session_binding_path(request.receipt_dir, request.session_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityError(
                "Codex app-server session has no durable tool-registry binding"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or value.get("thread_id") != request.session_id
            or value.get("tool_fingerprint") != fingerprint
            or value.get("adapter_version") != self.capabilities.version
            or value.get("instruction_mode") != "collaboration-mode-v1"
        ):
            raise CapabilityError(
                "Codex app-server session tool-registry binding does not match "
                "the requested authority or role-instruction mode"
            )
        return CodexAppServerSession(request.session_id, fingerprint)

    def _save_session(
        self, request: ProviderRequest, session: CodexAppServerSession
    ) -> None:
        _atomic_json(
            _session_binding_path(request.receipt_dir, session.thread_id),
            {
                "version": 1,
                "provider": self.name,
                "adapter_version": self.capabilities.version,
                "source_commit": PINNED_CODEX_COMMIT,
                "instruction_mode": "collaboration-mode-v1",
                "thread_id": session.thread_id,
                "tool_fingerprint": session.tool_fingerprint,
                "updated_at": _now(),
            },
        )


__all__ = [
    "AUDITED_CONFIG_OVERRIDES",
    "CODEX_APPSERVER_CAPABILITIES",
    "CodexAppServerBridge",
    "CodexAppServerCapabilityError",
    "CodexAppServerError",
    "CodexAppServerProtocolError",
    "CodexAppServerProvider",
    "CodexAppServerResult",
    "CodexAppServerSession",
    "DynamicTool",
    "PINNED_CODEX_COMMIT",
    "PINNED_CODEX_TAG",
    "PINNED_CODEX_VERSION",
    "UNAVOIDABLE_INTERNAL_TOOLS",
    "tool_fingerprint",
]
