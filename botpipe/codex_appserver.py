"""Codex app-server bridge for native and Botpipe-mediated turns."""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import stat
import subprocess
import tempfile
import threading
import time
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .native_tools import (
    ExactCommandTools,
    ReadOnlyTools,
    ToolObservation,
    command_scope_is_workspace_wide,
)
from .policy import NetworkMode, OperationKind, PermissionMode, SandboxMode
from .processes import ProcessContainment, ProcessContainmentUnavailable
from .providers import (
    CapabilityError,
    CODEX_APPSERVER_CAPABILITIES,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
    _CLIProvider,
    _NATIVE_EVENT_SINK,
    _atomic_json,
    _now,
    _read_receipt,
    _record_response,
    _receipt_path_for,
    _receipt_matches,
    _response_record,
    receipt_path,
)
from .recovery import Completed, RecoveryOutcome, Running, Stopped, Unknown
from .tool_evidence import ToolEvidence


CURRENT_VERIFIED_CODEX_VERSION = "0.155.1"
CURRENT_VERIFIED_CODEX_COMMIT = "be2951ea34f0d295ed0becf97079f92fa5f6950e"
MINIMUM_NATIVE_CODEX_VERSION = (0, 155, 1)
VERIFIED_MEDIATED_MODELS = frozenset({"gpt-5.4"})
_REVIEWED_MEDIATED_RELEASES = MappingProxyType(
    {CURRENT_VERIFIED_CODEX_VERSION: CURRENT_VERIFIED_CODEX_COMMIT}
)
TOOL_CALL_LIMIT = 16
TOOL_OUTPUT_BYTES = 32_000
_MAX_NATIVE_CONFIG_BYTES = 1_000_000
_BOTPIPE_ROLE_PREFIX = (
    "Botpipe role update: earlier Botpipe role instructions are no longer active. "
    "Follow these role instructions until another Botpipe role update:\n\n"
)
_BOTPIPE_ROLE_RESET = (
    "Botpipe role update: earlier Botpipe role instructions are no longer active. "
    "No additional Botpipe role instructions apply; continue under the provider's "
    "base and developer instructions."
)

# Current Codex can disable these tools.  Keep the names reserved so a dynamic
# registry cannot become ambiguous on a release with a different config result.
NATIVE_TOOL_NAMES = frozenset({"update_plan", "request_user_input"})
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
            raise ValueError("dynamic tool name is reserved by the native protocol")
        if self.namespace is not None and (
            self.namespace == "mcp"
            or self.namespace.startswith("mcp__")
            or self.namespace in _RESERVED_NAMESPACES
        ):
            raise ValueError("dynamic tool namespace is reserved by the native protocol")
        if self.namespace is None and self.name in NATIVE_TOOL_NAMES:
            raise ValueError("dynamic tool name collides with a native tool")
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
    codex_version: str
    usage: Mapping[str, Any] = field(default_factory=dict)
    events: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class CodexTurnProfile:
    """Complete per-turn execution authority and inventory contract."""

    name: str
    environments: tuple[Mapping[str, Any], ...]
    approval_policy: str
    sandbox_mode: str
    sandbox_policy: Mapping[str, Any]
    config: Mapping[str, Any]
    native_tools: bool = False

    def fingerprint_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "environments": [dict(value) for value in self.environments],
            "approval_policy": self.approval_policy,
            "sandbox_mode": self.sandbox_mode,
            "sandbox_policy": dict(self.sandbox_policy),
            "config": dict(self.config),
            "native_tools": self.native_tools,
        }


Mediator = Callable[[str, Mapping[str, Any]], object]
EventSink = Callable[[Mapping[str, Any]], None]


class CodexLifecycleStage(str, Enum):
    """Durable boundaries around one owned app-server process and turn."""

    SPAWN_INTENT = "spawn_intent"
    CONTAINED_SPAWN = "contained_spawn"
    THREAD_BOUND = "thread_binding"
    TURN_INTENT = "turn_intent"
    TURN_ACKNOWLEDGED = "turn_acknowledged"
    RECEIVED_RESPONSE = "received_response"
    PROCESS_QUIESCENT = "process_quiescent"
    CLEANUP_FAILED = "cleanup_failure"


@dataclass(frozen=True, slots=True)
class CodexLifecycleEvent:
    """One small synchronous lifecycle update persisted by the provider."""

    stage: CodexLifecycleStage
    thread_id: str | None = None
    turn_id: str | None = None
    result: CodexAppServerResult | None = None
    error: str | None = None


LifecycleCallback = Callable[[CodexLifecycleEvent], None]


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


def _is_native_project_trust_state(path: Path) -> bool:
    """Accept only Codex's bounded project-trust bookkeeping."""
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > _MAX_NATIVE_CONFIG_BYTES
        ):
            return False
        with path.open("rb") as handle:
            encoded = handle.read(_MAX_NATIVE_CONFIG_BYTES + 1)
        if len(encoded) > _MAX_NATIVE_CONFIG_BYTES:
            return False
        document = tomllib.loads(encoded.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    if set(document) != {"projects"}:
        return False
    projects = document["projects"]
    return isinstance(projects, dict) and all(
        isinstance(project, str)
        and bool(project)
        and isinstance(settings, dict)
        and settings == {"trust_level": "trusted"}
        for project, settings in projects.items()
    )


def _turn_fingerprint(
    tools: Sequence[DynamicTool], profile: CodexTurnProfile
) -> str:
    encoded = json.dumps(
        {
            "tools": [tool.to_wire() for tool in tools],
            "profile": profile.fingerprint_record(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _role_collaboration_mode(
    thread_response: Mapping[str, Any],
    instructions: str | None,
    *,
    model: str | None = None,
    effort: str | None = None,
) -> dict[str, Any]:
    model = model or thread_response.get("model")
    reasoning_effort = effort or thread_response.get("reasoningEffort")
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
    """Return conditional-tool closures verified against Codex 0.155.1."""
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
        "skill_search",
        "recommended_plugins",
        "token_budget",
        "current_time_reminder",
        "sleep_tool",
        "deferred_executor",
    )
    result = {f"features.{name}": False for name in disabled_features}
    result.update(
        {
            "web_search": "disabled",
            "project_doc_max_bytes": 0,
            "include_permissions_instructions": False,
            "tools.experimental_request_user_input.enabled": False,
            "tools.update_plan.enabled": False,
            "orchestrator.skills.enabled": False,
            "skills.include_instructions": False,
            "skills.bundled.enabled": False,
            "project_root_markers": [],
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
            self.process = self.containment.spawn(
                tuple(command),
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
            )
        except BaseException:
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
                # cannot outlive the successful response.  Allow the same
                # bounded kernel teardown interval used by other core callers;
                # Windows Job accounting can lag termination by over 100 ms.
                self.containment.finish(
                    self.process, grace_seconds=1.0, forced=True
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
    """Bidirectional client for the current app-server protocol."""

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
        self._schema_verified_version: str | None = None
        self.installed_version: str | None = None

    def preflight(
        self,
        workspace: Path,
        *,
        strict_inventory: bool = True,
        model: str | None = None,
    ) -> None:
        """Validate all locally knowable constraints before budget dispatch."""
        self.verify_installation(strict_inventory=strict_inventory)
        if strict_inventory and model not in (None, *VERIFIED_MEDIATED_MODELS):
            raise CodexAppServerCapabilityError(
                f"Codex mediated inventory is reviewed only for models "
                f"{sorted(VERIFIED_MEDIATED_MODELS)!r}; requested {model!r}"
            )
        try:
            ProcessContainment.require_available()
        except ProcessContainmentUnavailable as exc:
            raise CodexAppServerCapabilityError(
                f"Codex app-server process containment is unavailable: {exc}"
            ) from exc
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
        try:
            state.close()
        except BaseException:
            return "cleanup-failed"
        return "turn-interrupt" if requested else "contained"

    def is_active(self, owner_id: str) -> bool:
        with self._active_lock:
            return owner_id in self._active

    def verify_installation(self, *, strict_inventory: bool = True) -> None:
        """Check protocol support and, when needed, reviewed strict inventory."""
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
        match = re.search(
            r"(?:codex-cli\s+)?([0-9]+)\.([0-9]+)\.([0-9]+)$",
            version_text.strip(),
        )
        if match is None:
            raise CodexAppServerCapabilityError(
                f"could not determine Codex app-server protocol version from {version_text!r}"
            )
        version = ".".join(match.groups())
        self.installed_version = version
        parsed = tuple(map(int, match.groups()))
        if parsed < MINIMUM_NATIVE_CODEX_VERSION:
            raise CodexAppServerCapabilityError(
                "Codex app-server lacks the required per-turn environment, sandbox, "
                f"and collaboration capabilities; found {version!r}"
            )
        if strict_inventory and version not in _REVIEWED_MEDIATED_RELEASES:
            raise CodexAppServerCapabilityError(
                "strict mediated tool inventory has no conformance evidence for "
                f"codex-cli {version}; native RUN remains available when its protocol "
                "capability check succeeds"
            )
        if (
            self.version_probe is None
            and self._schema_verified_version != version
        ):
            self._verify_protocol_schema()
            self._schema_verified_version = version
        self._verify_config_hygiene()

    def _verify_protocol_schema(self) -> None:
        """Generate the installed schema and require every field Botpipe emits."""
        executable = self.version_command[0]
        with tempfile.TemporaryDirectory(prefix="botpipe-codex-schema-") as directory:
            try:
                subprocess.run(
                    (
                        executable,
                        "app-server",
                        "generate-json-schema",
                        "--experimental",
                        "--out",
                        directory,
                    ),
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=30,
                    env={
                        **os.environ,
                        **self.env,
                        "CODEX_HOME": str(self.codex_home),
                    },
                )
                schema_root = Path(directory) / "v2"
                requirements = {
                    "ThreadStartParams.json": {
                        "approvalPolicy",
                        "config",
                        "dynamicTools",
                        "environments",
                        "model",
                        "sandbox",
                    },
                    "ThreadResumeParams.json": {
                        "approvalPolicy",
                        "config",
                        "model",
                        "sandbox",
                    },
                    "TurnStartParams.json": {
                        "approvalPolicy",
                        "collaborationMode",
                        "environments",
                        "model",
                        "outputSchema",
                        "sandboxPolicy",
                    },
                }
                missing: list[str] = []
                for filename, fields in requirements.items():
                    document = json.loads(
                        (schema_root / filename).read_text(encoding="utf-8")
                    )
                    properties = document.get("properties")
                    if not isinstance(properties, Mapping):
                        missing.append(f"{filename}:properties")
                        continue
                    missing.extend(
                        f"{filename}:{field}"
                        for field in sorted(fields - set(properties))
                    )
            except (
                OSError,
                subprocess.SubprocessError,
                json.JSONDecodeError,
                KeyError,
            ) as exc:
                raise CodexAppServerCapabilityError(
                    f"Codex protocol schema capability probe failed: {exc}"
                ) from exc
        if missing:
            raise CodexAppServerCapabilityError(
                "Codex protocol schema is missing required capabilities: "
                + ", ".join(missing)
            )

    def _verify_config_hygiene(self) -> None:
        # A private home may contain auth and model cache, but none of the
        # surfaces that can register tools or spawn lifecycle hooks.
        effective_env = {**os.environ, **self.env}
        home_roots = [Path.home()]
        for name in ("HOME", "USERPROFILE"):
            value = effective_env.get(name)
            if value:
                home_roots.append(Path(value).expanduser())
        unique_home_roots = tuple(dict.fromkeys(path.resolve() for path in home_roots))
        prohibited = (
            self.codex_home / "hooks.json",
            self.codex_home / "plugins",
            self.codex_home / ".agents" / "skills",
            *(root / ".agents" / "skills" for root in unique_home_roots),
            Path("/etc/codex/skills"),
        )
        present = [str(path) for path in prohibited if path.exists()]
        user_config = self.codex_home / "config.toml"
        if (user_config.exists() or user_config.is_symlink()) and not (
            _is_native_project_trust_state(user_config)
        ):
            present.append(str(user_config))
        skill_root = self.codex_home / "skills"
        if skill_root.exists():
            present.extend(
                str(path)
                for path in skill_root.iterdir()
                if path.name != ".system" or path.is_symlink()
            )
        system = Path("/etc/codex/config.toml")
        if system.exists():
            present.append(str(system))
        if present:
            raise CodexAppServerCapabilityError(
                "Codex profile requires an isolated configuration home; "
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
        profile: CodexTurnProfile | None = None,
        effort: str | None = None,
        lifecycle: LifecycleCallback | None = None,
    ) -> CodexAppServerResult:
        """Run one turn under an explicit semantic execution profile."""
        self._validate_execute(
            prompt, workspace, tools, mediator, timeout, output_schema, session
        )
        if owner_id is not None and not owner_id:
            raise ValueError("owner_id must be non-empty when provided")
        root = Path(workspace).resolve(strict=True)
        if profile is None:
            profile = CodexTurnProfile(
                name="mediated-v2",
                environments=(),
                approval_policy="never",
                sandbox_mode="read-only",
                sandbox_policy=MappingProxyType(
                    {"type": "readOnly", "networkAccess": False}
                ),
                config=AUDITED_CONFIG_OVERRIDES,
            )
        self.preflight(
            root,
            strict_inventory=not profile.native_tools,
            model=model,
        )
        fingerprint = registry_fingerprint or _turn_fingerprint(tools, profile)
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

        if lifecycle is not None and not callable(lifecycle):
            raise TypeError("lifecycle must be callable or None")

        environment = {
            **os.environ,
            **self.env,
            "CODEX_HOME": str(self.codex_home),
            "RUST_LOG": "error",
            "LOG_FORMAT": "json",
        }
        if not profile.native_tools:
            environment.update(
                HOME=str(self.codex_home),
                USERPROFILE=str(self.codex_home),
            )
        if lifecycle is not None:
            # This write precedes process creation.  A prepared receipt without
            # this boundary therefore proves that no native process was spawned.
            lifecycle(CodexLifecycleEvent(CodexLifecycleStage.SPAWN_INTENT))
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
            native_tools=profile.native_tools,
            lifecycle=lifecycle,
        )
        try:
            state.emit_lifecycle(
                CodexLifecycleEvent(CodexLifecycleStage.CONTAINED_SPAWN)
            )
        except BaseException:
            state.close()
            raise
        if owner_id is not None:
            with self._active_lock:
                if owner_id in self._active:
                    state.close()
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
                    "approvalPolicy": profile.approval_policy,
                    "sandbox": profile.sandbox_mode,
                    "ephemeral": False,
                    "environments": [dict(value) for value in profile.environments],
                    "dynamicTools": [tool.to_wire() for tool in tools],
                    "config": dict(profile.config),
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
                        "model": model,
                        "approvalPolicy": profile.approval_policy,
                        "sandbox": profile.sandbox_mode,
                        "config": dict(profile.config),
                    },
                )
                thread_response = resumed
                thread = resumed.get("thread")
                thread_id = thread.get("id") if isinstance(thread, Mapping) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise CodexAppServerProtocolError("thread response contained no thread id")
            state.thread_id = thread_id
            state.emit_lifecycle(
                CodexLifecycleEvent(
                    CodexLifecycleStage.THREAD_BOUND,
                    thread_id=thread_id,
                )
            )
            if not profile.native_tools:
                effective_model = thread_response.get("model")
                if effective_model not in VERIFIED_MEDIATED_MODELS:
                    raise CodexAppServerCapabilityError(
                        "strict mediated tool inventory has no model-catalog "
                        f"conformance evidence for effective model {effective_model!r}; "
                        f"reviewed models are {sorted(VERIFIED_MEDIATED_MODELS)!r}"
                    )
            collaboration_mode = _role_collaboration_mode(
                thread_response,
                instructions,
                model=model,
                effort=effort,
            )
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "environments": [dict(value) for value in profile.environments],
                "approvalPolicy": profile.approval_policy,
                "sandboxPolicy": dict(profile.sandbox_policy),
                "collaborationMode": collaboration_mode,
                "outputSchema": (
                    _plain_json(output_schema, label="output schema")
                    if output_schema is not None
                    else None
                ),
            }
            state.emit_lifecycle(
                CodexLifecycleEvent(
                    CodexLifecycleStage.TURN_INTENT,
                    thread_id=thread_id,
                )
            )
            turn_started = state.rpc(
                "turn/start",
                {key: value for key, value in turn_params.items() if value is not None},
            )
            turn = turn_started.get("turn")
            turn_id = turn.get("id") if isinstance(turn, Mapping) else None
            if not isinstance(turn_id, str) or not turn_id:
                raise CodexAppServerProtocolError("turn/start contained no turn id")
            state.turn_id = turn_id
            state.emit_lifecycle(
                CodexLifecycleEvent(
                    CodexLifecycleStage.TURN_ACKNOWLEDGED,
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
            )
            text, usage = state.wait_for_terminal()
            result = CodexAppServerResult(
                text=text,
                session=CodexAppServerSession(thread_id, fingerprint),
                turn_id=turn_id,
                codex_version=self.installed_version or "unknown",
                usage=MappingProxyType(usage),
                events=tuple(MappingProxyType(dict(event)) for event in state.events),
            )
            state.emit_lifecycle(
                CodexLifecycleEvent(
                    CodexLifecycleStage.RECEIVED_RESPONSE,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    result=result,
                )
            )
            return result
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
            state.close()

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
        workspace_skills = workspace / ".agents" / "skills"
        if workspace_skills.exists():
            raise CodexAppServerCapabilityError(
                "workspace host skills are unavailable to the mediated profile: "
                f"{workspace_skills}"
            )
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
    native_tools: bool = False
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
    lifecycle: LifecycleCallback | None = None
    lifecycle_close_lock: threading.RLock = field(default_factory=threading.RLock)
    quiescence_recorded: bool = False

    def emit_lifecycle(self, event: CodexLifecycleEvent) -> None:
        with self.lifecycle_close_lock:
            if self.quiescence_recorded:
                raise CodexAppServerProtocolError(
                    "Codex lifecycle cannot advance after process-tree cleanup"
                )
            if self.lifecycle is not None:
                self.lifecycle(event)

    def close(self) -> None:
        """Close the owned tree and durably report exactly what close proved."""
        with self.lifecycle_close_lock:
            if self.quiescence_recorded:
                return
            try:
                self.process.close()
            except BaseException as exc:
                try:
                    self.emit_lifecycle(
                        CodexLifecycleEvent(
                            CodexLifecycleStage.CLEANUP_FAILED,
                            thread_id=self.thread_id,
                            turn_id=self.turn_id,
                            error=str(exc),
                        )
                    )
                except BaseException:
                    # The cleanup failure remains the controlling evidence.  A
                    # second receipt-write failure cannot make it safer.
                    pass
                raise
            self.emit_lifecycle(
                CodexLifecycleEvent(
                    CodexLifecycleStage.PROCESS_QUIESCENT,
                    thread_id=self.thread_id,
                    turn_id=self.turn_id,
                )
            )
            self.quiescence_recorded = True

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
        if self.native_tools:
            return
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
        if self.native_tools and method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            self.process.send({"id": request_id, "result": {"decision": "decline"}})
            return
        if self.native_tools and method == "item/tool/requestUserInput":
            self.process.send({"id": request_id, "result": {"answers": {}}})
            return
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
    operation: OperationKind,
    turn_profile: CodexTurnProfile,
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
        "transport": "codex-app-server-v2",
        "operation": operation.value,
        "turn_profile": turn_profile.fingerprint_record(),
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
    """Provider adapter using one app-server transport for every operation."""

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
        env: Mapping[str, str] | None = None,
        bridge: CodexAppServerBridge | None = None,
    ) -> None:
        super().__init__(("codex-app-server",), env=env)
        if bridge is None:
            selected_home = codex_home or (env or {}).get("BOTPIPE_CODEX_HOME")
            if selected_home is None:
                raise ValueError(
                    "Codex app-server profile requires an isolated codex_home "
                    "containing credentials but no external tool configuration"
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
        self._active_receipts_lock = threading.Lock()
        self._active_receipts: dict[str, tuple[ProviderRequest, Path]] = {}

    def validate_request(self, request: ProviderRequest) -> None:
        super().validate_request(request)
        if request.operation is OperationKind.RUN:
            self._native_profile(request)
        elif request.operation is OperationKind.GENERATE and request.allow_commands:
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
        policy = request.policy.effective()
        self.bridge.preflight(
            request.workspace,
            strict_inventory=request.operation is not OperationKind.RUN,
            model=policy.model,
        )

    def cancel(self, operation_id: str) -> RecoveryOutcome:
        with self._active_receipts_lock:
            active = self._active_receipts.get(operation_id)
        attempted = self.bridge.interrupt(operation_id, timeout=2.0)
        if attempted == "cleanup-failed":
            return Unknown(
                f"Codex app-server attempt {operation_id!r}: owned process-tree "
                "cleanup could not be confirmed"
            )
        if attempted is not None:
            if active is not None:
                request, path = active
                try:
                    value = _read_receipt(path)
                except ProviderInterruptedError as exc:
                    return Unknown(str(exc))
                return self._receipt_outcome(request, value, path)
            return Stopped(
                f"Codex app-server attempt {operation_id!r}: cleanup proves it "
                "cannot continue but does not rule out earlier effects"
            )
        return Unknown(
            f"Codex app-server attempt {operation_id!r}: no owned active app-server "
            "process was found; terminal quiescence was not independently acknowledged"
        )

    @staticmethod
    def _stage_record(
        value: Mapping[str, Any], stage: CodexLifecycleStage
    ) -> Mapping[str, Any] | None:
        record = value.get(stage.value)
        if record is None:
            return None
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("at"), str)
            or not isinstance(record.get("sequence"), int)
            or isinstance(record.get("sequence"), bool)
            or record["sequence"] < 1
        ):
            raise ValueError(f"invalid {stage.value} evidence")
        return record

    @classmethod
    def _receipt_outcome(
        cls, request: ProviderRequest, value: Mapping[str, Any], path: Path
    ) -> RecoveryOutcome:
        """Interpret one exact v2 lifecycle receipt, failing closed."""
        if value.get("version") != 2:
            return Unknown("Codex lifecycle receipt has an unsupported schema")
        try:
            stages = {
                stage: cls._stage_record(value, stage) for stage in CodexLifecycleStage
            }
        except ValueError as exc:
            return Unknown(str(exc))
        if value.get("lifecycle_conflict") is not None:
            return Unknown("Codex receipt has conflicting lifecycle evidence")
        sequences = [record["sequence"] for record in stages.values() if record]
        if len(sequences) != len(set(sequences)):
            return Unknown("Codex lifecycle sequence contains duplicates")
        ordered = [
            CodexLifecycleStage.SPAWN_INTENT,
            CodexLifecycleStage.CONTAINED_SPAWN,
            CodexLifecycleStage.THREAD_BOUND,
            CodexLifecycleStage.TURN_INTENT,
            CodexLifecycleStage.TURN_ACKNOWLEDGED,
            CodexLifecycleStage.RECEIVED_RESPONSE,
            CodexLifecycleStage.PROCESS_QUIESCENT,
        ]
        ordered_sequences = [
            stages[stage]["sequence"] for stage in ordered if stages[stage] is not None
        ]
        if ordered_sequences != sorted(ordered_sequences):
            return Unknown("Codex lifecycle stage order is invalid")

        spawn = stages[CodexLifecycleStage.SPAWN_INTENT]
        quiescent = stages[CodexLifecycleStage.PROCESS_QUIESCENT]
        cleanup_failure = stages[CodexLifecycleStage.CLEANUP_FAILED]
        received = stages[CodexLifecycleStage.RECEIVED_RESPONSE]
        if spawn is None:
            if any(record is not None for record in stages.values()):
                return Unknown("Codex lifecycle evidence exists without spawn intent")
            return Stopped("Codex attempt was prepared but native spawn was not authorized")
        if cleanup_failure is not None and (
            quiescent is None or cleanup_failure["sequence"] > quiescent["sequence"]
        ):
            return Unknown("Codex owned process-tree cleanup was not confirmed")
        response = value.get("response")
        if response is not None:
            if received is None:
                return Unknown("Codex response exists without received-response evidence")
            if quiescent is None:
                return Unknown(
                    "Codex response is durable but process-tree quiescence is unproven"
                )
            if received["sequence"] >= quiescent["sequence"]:
                return Unknown("Codex response/quiescence lifecycle order is invalid")
            thread_id = received.get("thread_id")
            turn_id = received.get("turn_id")
            binding = stages[CodexLifecycleStage.THREAD_BOUND]
            turn_intent = stages[CodexLifecycleStage.TURN_INTENT]
            turn_ack = stages[CodexLifecycleStage.TURN_ACKNOWLEDGED]
            if (
                binding is None
                or turn_intent is None
                or turn_ack is None
                or not isinstance(thread_id, str)
                or not thread_id
                or not isinstance(turn_id, str)
                or not turn_id
                or binding.get("thread_id") != thread_id
                or turn_intent.get("thread_id") != thread_id
                or turn_ack.get("thread_id") != thread_id
                or turn_ack.get("turn_id") != turn_id
                or value.get("session_id") != thread_id
                or value.get("turn_id") != turn_id
            ):
                return Unknown("Codex terminal response identity is inconsistent")
            try:
                return Completed(_record_response(response, path))
            except ProviderInterruptedError as exc:
                return Unknown(str(exc))
        if received is not None:
            return Unknown("Codex received-response evidence has no typed response")
        if quiescent is not None:
            return Stopped(
                "Codex owned process tree is quiescent; earlier effects may have occurred"
            )
        return Unknown("Codex native attempt may have started and quiescence is unproven")

    def _history(
        self, request: ProviderRequest
    ) -> list[tuple[int, Mapping[str, Any] | None, Path, RecoveryOutcome]]:
        history: list[tuple[int, Mapping[str, Any] | None, Path, RecoveryOutcome]] = []
        for attempt in range(request.attempt, 0, -1):
            path = _receipt_path_for(request, attempt)
            if not path.exists():
                continue
            try:
                value = _read_receipt(path)
            except ProviderInterruptedError as exc:
                history.append((attempt, None, path, Unknown(str(exc))))
                continue
            if not _receipt_matches(value, request, attempt):
                outcome: RecoveryOutcome = Unknown(
                    f"Codex receipt identity does not match attempt {attempt}"
                )
            else:
                outcome = self._receipt_outcome(request, value, path)
            history.append((attempt, value, path, outcome))
        return history

    def _reduce_history(
        self,
        request: ProviderRequest,
        history: Sequence[tuple[int, Mapping[str, Any] | None, Path, RecoveryOutcome]],
    ) -> RecoveryOutcome:
        with self._active_receipts_lock:
            active = self._active_receipts.get(request.operation_id)
        if active is not None:
            active_request, _path = active
            active_terminal = any(
                attempt == active_request.attempt
                and isinstance(value, Mapping)
                and isinstance(value.get("process_quiescent"), Mapping)
                and isinstance(outcome, (Completed, Stopped))
                for attempt, value, _path, outcome in history
            )
            if not active_terminal:
                return Running(f"Codex attempt {request.operation_id!r} is active")
        for _attempt, _value, _path, outcome in history:
            if isinstance(outcome, Running):
                return outcome
            if isinstance(outcome, Unknown):
                if self.bridge.is_active(request.operation_id):
                    return Running(f"Codex attempt {request.operation_id!r} is active")
                return outcome
        completed = [
            outcome
            for _attempt, _value, _path, outcome in history
            if isinstance(outcome, Completed)
        ]
        if completed:
            records = [item.response.to_record() for item in completed]
            if any(record != records[0] for record in records[1:]):
                return Unknown("Codex attempts contain conflicting completed responses")
            return completed[0]
        for _attempt, _value, _path, outcome in history:
            if isinstance(outcome, Stopped):
                return outcome
        if self.bridge.is_active(request.operation_id):
            return Running(f"Codex attempt {request.operation_id!r} is active")
        return Unknown("no matching Codex lifecycle receipt")

    def recover(self, request: ProviderRequest) -> RecoveryOutcome:
        return self._reduce_history(request, self._history(request))

    def _reconcile_codex_attempts(
        self, request: ProviderRequest
    ) -> tuple[ProviderResponse | None, Mapping[str, Any] | None]:
        """Use the recovery reducer as the single retry authorization gate."""
        history = self._history(request)
        outcome = self._reduce_history(request, history)
        if isinstance(outcome, Completed):
            return outcome.response, None  # type: ignore[return-value]
        if isinstance(outcome, Running) or (isinstance(outcome, Unknown) and history):
            raise ProviderInterruptedError(
                outcome.detail or "Codex attempt is not safely retryable",
                receipt=history[0][2] if history else receipt_path(request),
            )
        current_exists = any(attempt == request.attempt for attempt, *_rest in history)
        if current_exists:
            raise ProviderError(
                "Codex attempt is already stopped; authorize a new attempt to retry"
            )
        resume = next(
            (
                value
                for _attempt, value, _path, item in history
                if isinstance(item, Stopped)
                and isinstance(value, Mapping)
                and isinstance(
                    value.get(CodexLifecycleStage.THREAD_BOUND.value), Mapping
                )
            ),
            None,
        )
        return None, resume

    def run(self, request: ProviderRequest) -> ProviderResponse:
        self.validate_request(request)
        prior, resume_receipt = self._reconcile_codex_attempts(request)
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
            turn_profile = (
                self._native_profile(request)
                if request.operation is OperationKind.RUN
                else self._mediated_profile()
            )
            fingerprint = _profile_fingerprint(
                tools,
                envelopes,
                operation=request.operation,
                turn_profile=turn_profile,
                read_roots=roots,
                read_exclusions=exclusions,
            )
            resume_thread_id: str | None = None
            if resume_receipt is not None:
                binding = resume_receipt[CodexLifecycleStage.THREAD_BOUND.value]
                candidate = binding.get("thread_id")
                if not isinstance(candidate, str) or not candidate:
                    raise ProviderInterruptedError(
                        "prior quiescent Codex receipt has an invalid thread binding"
                    )
                if resume_receipt.get("tool_fingerprint") != fingerprint:
                    raise CapabilityError(
                        "prior Codex thread is bound to a different execution profile"
                    )
                resume_thread_id = candidate
                if request.session_id not in (None, resume_thread_id):
                    raise CapabilityError(
                        "authorized Codex retry cannot replace the prior attempt's thread"
                    )
            session = self._load_session(
                request,
                fingerprint,
                thread_id=resume_thread_id or request.session_id,
            )
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
            "version": 2,
            "provider": self.name,
            "adapter_version": self.capabilities.version,
            "codex_version": self.bridge.installed_version,
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "operation": request.operation.value,
            "tool_fingerprint": fingerprint,
            "status": "prepared",
            "prepared_at": _now(),
        }
        receipt_lock = threading.RLock()
        response: ProviderResponse | None = None

        def record_lifecycle(event: CodexLifecycleEvent) -> None:
            nonlocal response
            with receipt_lock:
                current = _read_receipt(path)
                if not _receipt_matches(current, request, request.attempt):
                    raise ProviderInterruptedError(
                        "Codex lifecycle receipt identity changed during execution",
                        receipt=path,
                    )
                key = event.stage.value
                record: dict[str, Any] = {"at": _now()}
                if event.thread_id is not None:
                    record["thread_id"] = event.thread_id
                if event.turn_id is not None:
                    record["turn_id"] = event.turn_id
                if event.error is not None:
                    record["error"] = event.error
                existing_event = current.get(key)
                if isinstance(existing_event, Mapping):
                    comparable = {
                        name: value
                        for name, value in existing_event.items()
                        if name not in {"at", "sequence"}
                    }
                    proposed = {
                        name: value
                        for name, value in record.items()
                        if name != "at"
                    }
                    if comparable != proposed:
                        current["lifecycle_conflict"] = {
                            "stage": key,
                            "at": _now(),
                        }
                        current["status"] = "uncertain"
                        _atomic_json(path, current)
                        raise ProviderInterruptedError(
                            f"conflicting Codex lifecycle event for {key}", receipt=path
                        )
                    return
                sequence = current.get("lifecycle_sequence", 0)
                if not isinstance(sequence, int) or sequence < 0:
                    raise ProviderInterruptedError(
                        "Codex lifecycle sequence is malformed", receipt=path
                    )
                record["sequence"] = sequence + 1

                if event.stage is CodexLifecycleStage.THREAD_BOUND:
                    if event.thread_id is None:
                        raise CodexAppServerProtocolError(
                            "thread lifecycle event has no thread id"
                        )
                    self._save_session(
                        request, CodexAppServerSession(event.thread_id, fingerprint)
                    )
                elif event.stage is CodexLifecycleStage.RECEIVED_RESPONSE:
                    if event.result is None:
                        raise CodexAppServerProtocolError(
                            "response lifecycle event has no typed result"
                        )
                    response = ProviderResponse(
                        event.result.text,
                        event.result.session.thread_id,
                        self._usage(event.result.usage),
                        {
                            "provider": self.name,
                            "adapter_version": self.capabilities.version,
                            "codex_version": event.result.codex_version,
                            "tool_fingerprint": fingerprint,
                            "tool_observations": [
                                item.to_record() for item in observations
                            ],
                        },
                    )
                    current["response"] = _response_record(response)
                    current["session_id"] = event.result.session.thread_id
                    current["turn_id"] = event.result.turn_id

                current[key] = record
                current["lifecycle_sequence"] = sequence + 1
                quiescent = isinstance(
                    current.get(CodexLifecycleStage.PROCESS_QUIESCENT.value), Mapping
                )
                failed_cleanup = isinstance(
                    current.get(CodexLifecycleStage.CLEANUP_FAILED.value), Mapping
                )
                if quiescent:
                    current["status"] = (
                        "completed" if "response" in current else "stopped"
                    )
                    current["finished_at"] = _now()
                elif failed_cleanup:
                    current["status"] = "uncertain"
                    current["finished_at"] = _now()
                elif event.stage is CodexLifecycleStage.SPAWN_INTENT:
                    current["status"] = "dispatching"
                    current["dispatched_at"] = _now()
                else:
                    current["status"] = "running"
                _atomic_json(path, current)

        registered = False
        try:
            with self._active_receipts_lock:
                if request.operation_id in self._active_receipts:
                    raise CodexAppServerCapabilityError(
                        f"Codex operation {request.operation_id!r} is already active"
                    )
                _atomic_json(path, started)
                self._active_receipts[request.operation_id] = (request, path)
                registered = True
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
                profile=turn_profile,
                effort=policy.effort.value if policy.effort is not None else None,
                lifecycle=record_lifecycle,
            )
            if response is None:
                raise CodexAppServerProtocolError(
                    "Codex bridge returned without a durable response callback"
                )
        except (KeyboardInterrupt, SystemExit):
            dispatch.finish("interrupted")
            raise
        except CodexAppServerCapabilityError as exc:
            if registered:
                self._record_run_error(path, request, str(exc))
            dispatch.finish("failed", error=exc)
            raise CapabilityError(str(exc)) from exc
        except BaseException as exc:
            detail = f"Codex app-server terminal result was not committed: {exc}"
            if registered:
                self._record_run_error(path, request, detail)
            dispatch.finish("failed", error=exc)
            raise ProviderInterruptedError(detail, receipt=path) from exc
        finally:
            with self._active_receipts_lock:
                if registered and self._active_receipts.get(request.operation_id) == (request, path):
                    del self._active_receipts[request.operation_id]
            for cleanup in cleanups:
                cleanup()
        assert response is not None
        dispatch.finish("completed", usage=response.usage)
        return response

    @staticmethod
    def _record_run_error(
        path: Path, request: ProviderRequest, detail: str
    ) -> None:
        """Attach an error without discarding stronger durable milestones."""
        try:
            current = _read_receipt(path)
            if not _receipt_matches(current, request, request.attempt):
                return
            current["error"] = detail
            current["error_at"] = _now()
            if isinstance(
                current.get(CodexLifecycleStage.PROCESS_QUIESCENT.value), Mapping
            ):
                current["status"] = (
                    "completed" if "response" in current else "stopped"
                )
            elif current.get(CodexLifecycleStage.SPAWN_INTENT.value) is None:
                current["status"] = "failed"
            else:
                current["status"] = "uncertain"
            _atomic_json(path, current)
        except (OSError, ProviderInterruptedError):
            # The original failure remains controlling.  In particular, do not
            # replace a response or quiescence record with a weaker template.
            return

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
        if request.operation is OperationKind.RUN:
            commands = None
            envelopes = {}
            tools = []
        elif request.operation is OperationKind.QUERY:
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
        elif request.allow_commands:
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
        else:
            commands = None
            envelopes = {}
            tools = []

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
    def _mediated_profile() -> CodexTurnProfile:
        return CodexTurnProfile(
            name="mediated-strict-v2",
            environments=(),
            approval_policy="never",
            sandbox_mode="read-only",
            sandbox_policy=MappingProxyType(
                {"type": "readOnly", "networkAccess": False}
            ),
            config=AUDITED_CONFIG_OVERRIDES,
        )

    @staticmethod
    def _native_profile(request: ProviderRequest) -> CodexTurnProfile:
        policy = request.policy.effective()
        unsupported: list[str] = []
        if policy.provider is not None and policy.provider.value != "codex":
            unsupported.append(f"provider={policy.provider.value}")
        if policy.base_url is not None:
            unsupported.append("base_url")
        if policy.model_overrides:
            unsupported.append("model_overrides")
        if policy.allow_read not in (None, (".",)):
            unsupported.append("allow_read")
        workspace = request.workspace.resolve()

        def resolve_paths(values: Sequence[str]) -> list[str]:
            resolved: list[str] = []
            for value in values:
                raw = Path(value)
                path = raw.resolve() if raw.is_absolute() else (workspace / raw).resolve()
                if not raw.is_absolute() and not path.is_relative_to(workspace):
                    raise CapabilityError(
                        f"relative policy path escapes workspace: {value!r}"
                    )
                resolved.append(str(path))
            return resolved

        write_roots = resolve_paths(policy.allow_write or ())
        if (
            policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
            and str(workspace) not in write_roots
        ):
            unsupported.append(
                "allow_write (Codex workspace-write cannot narrow its working directory)"
            )
        for name in (
            "deny_read",
            "network_domains",
            "deny_network_domains",
            "allow_permissions",
            "ask_permissions",
            "deny_permissions",
        ):
            if getattr(policy, name):
                unsupported.append(name)
        if policy.deny_write and policy.sandbox_mode is not SandboxMode.READ_ONLY:
            unsupported.append("deny_write")
        if policy.network is NetworkMode.LIMITED:
            unsupported.append("network=limited")
        if (
            policy.sandbox_mode is SandboxMode.READ_ONLY
            and policy.network is NetworkMode.FULL
        ):
            unsupported.append("network=full under read_only sandbox")
        if (
            policy.sandbox_mode is SandboxMode.DANGER_FULL_ACCESS
            and policy.network is not NetworkMode.FULL
        ):
            unsupported.append(
                f"network={policy.network.value} under danger_full_access"
            )
        if policy.sandbox_mode is SandboxMode.DANGER_FULL_ACCESS and policy.allow_write:
            unsupported.append("allow_write under danger_full_access")
        if policy.sandbox_mode is SandboxMode.READ_ONLY and request.artifacts:
            unsupported.append("declared artifact writes under read_only sandbox")
        if policy.allow_local_binding:
            unsupported.append("allow_local_binding")
        if policy.permission_mode in (PermissionMode.AUTO_EDIT, PermissionMode.DENY_ALL):
            unsupported.append(f"permission_mode={policy.permission_mode.value}")
        if policy.verbosity is not None:
            unsupported.append("verbosity")
        if policy.reasoning_summary is not None:
            unsupported.append("reasoning_summary")
        if (
            policy.permission_mode is PermissionMode.FULL_AUTO_UNSANDBOXED
            and policy.sandbox_mode is not SandboxMode.DANGER_FULL_ACCESS
        ):
            unsupported.append("unsandboxed automation without danger_full_access")
        if unsupported:
            raise CapabilityError(
                "Codex app-server native RUN cannot enforce: "
                + ", ".join(unsupported)
            )
        approval = (
            "never"
            if policy.permission_mode
            in (
                PermissionMode.FULL_AUTO_SANDBOXED,
                PermissionMode.FULL_AUTO_UNSANDBOXED,
            )
            else "on-request"
        )
        if policy.sandbox_mode is SandboxMode.READ_ONLY:
            sandbox_mode = "read-only"
            sandbox_policy: dict[str, Any] = {
                "type": "readOnly",
                "networkAccess": False,
            }
        elif policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE:
            sandbox_mode = "workspace-write"
            artifact_roots = []
            for destination in request.artifacts.values():
                target = (
                    destination
                    if destination.is_absolute()
                    else workspace / destination
                )
                artifact_roots.append(str(target.resolve().parent))
            extra_roots = list(
                dict.fromkeys(
                    root
                    for root in (*write_roots, *artifact_roots)
                    if root != str(workspace)
                )
            )
            sandbox_policy = {
                "type": "workspaceWrite",
                "writableRoots": extra_roots,
                "networkAccess": policy.network is NetworkMode.FULL,
            }
        else:
            sandbox_mode = "danger-full-access"
            sandbox_policy = {"type": "dangerFullAccess"}
        environment = MappingProxyType(
            {
                "environmentId": "local",
                "cwd": str(workspace),
                "runtimeWorkspaceRoots": [str(workspace)],
            }
        )
        native_config: dict[str, Any] = {
            "skills.include_instructions": False,
            "skills.bundled.enabled": False,
            "orchestrator.skills.enabled": False,
            "project_root_markers": [],
        }
        if os.name == "nt":
            native_config["windows.sandbox"] = "unelevated"
        return CodexTurnProfile(
            name="native-run-v1",
            environments=(environment,),
            approval_policy=approval,
            sandbox_mode=sandbox_mode,
            sandbox_policy=MappingProxyType(sandbox_policy),
            config=MappingProxyType(native_config),
            native_tools=True,
        )

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
        self,
        request: ProviderRequest,
        fingerprint: str,
        *,
        thread_id: str | None = None,
    ) -> CodexAppServerSession | None:
        selected_thread = request.session_id if thread_id is None else thread_id
        if selected_thread is None:
            return None
        path = _session_binding_path(request.receipt_dir, selected_thread)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CapabilityError(
                "Codex app-server session has no durable tool-registry binding"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or value.get("thread_id") != selected_thread
            or value.get("tool_fingerprint") != fingerprint
            or value.get("adapter_version") != self.capabilities.version
            or value.get("instruction_mode") != "collaboration-mode-v1"
        ):
            raise CapabilityError(
                "Codex app-server session tool-registry binding does not match "
                "the requested authority or role-instruction mode"
            )
        return CodexAppServerSession(selected_thread, fingerprint)

    def _save_session(
        self, request: ProviderRequest, session: CodexAppServerSession
    ) -> None:
        _atomic_json(
            _session_binding_path(request.receipt_dir, session.thread_id),
            {
                "version": 1,
                "provider": self.name,
                "adapter_version": self.capabilities.version,
                "codex_version": self.bridge.installed_version,
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
    "CodexLifecycleEvent",
    "CodexLifecycleStage",
    "DynamicTool",
    "CURRENT_VERIFIED_CODEX_COMMIT",
    "CURRENT_VERIFIED_CODEX_VERSION",
    "MINIMUM_NATIVE_CODEX_VERSION",
    "NATIVE_TOOL_NAMES",
    "CodexTurnProfile",
    "tool_fingerprint",
]
