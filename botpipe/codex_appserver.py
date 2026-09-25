"""Thin JSONL adapter for the Codex app-server protocol."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import weakref
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
_TOOL_ENABLING_FEATURES = (
    frozenset(feature for features in _TOOL_FEATURES.values() for feature in features)
    | _DISABLED_ONLY_TOOL_FEATURES
)
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

_CODEX_PLATFORM_PACKAGES = {
    ("linux", "x86_64"): (
        "codex-linux-x64",
        "x86_64-unknown-linux-musl",
        "codex",
    ),
    ("linux", "aarch64"): (
        "codex-linux-arm64",
        "aarch64-unknown-linux-musl",
        "codex",
    ),
    ("darwin", "x86_64"): (
        "codex-darwin-x64",
        "x86_64-apple-darwin",
        "codex",
    ),
    ("darwin", "aarch64"): (
        "codex-darwin-arm64",
        "aarch64-apple-darwin",
        "codex",
    ),
    ("win32", "x86_64"): (
        "codex-win32-x64",
        "x86_64-pc-windows-msvc",
        "codex.exe",
    ),
    ("win32", "aarch64"): (
        "codex-win32-arm64",
        "aarch64-pc-windows-msvc",
        "codex.exe",
    ),
}


def _packaged_codex_binary(
    launcher: str | os.PathLike[str],
    *,
    platform_name: str | None = None,
    machine: str | None = None,
    search_path: str | None = None,
) -> Path | None:
    """Resolve an official npm launcher to the native binary it delegates to."""

    value = str(launcher)
    located = (
        shutil.which(value, path=search_path)
        if not Path(value).is_absolute() and Path(value).parent == Path(".")
        else value
    )
    if not located:
        return None
    lexical = Path(located).expanduser().absolute()
    try:
        resolved = lexical.resolve(strict=True)
    except OSError:
        return None
    package_roots: list[Path] = []
    recognized_launcher = False
    if resolved.name == "codex.js" and resolved.parent.name == "bin":
        recognized_launcher = True
        package_roots.append(resolved.parent.parent)
    # npm command shims contain this canonical package-relative entrypoint.
    # Inspect the marker only; never parse or execute an embedded path.
    launcher_name = lexical.name.lower()
    launcher_text = ""
    if launcher_name in {"codex.cmd", "codex.ps1"}:
        try:
            with lexical.open("rb") as handle:
                launcher_text = handle.read(65536).decode(errors="replace")
            launcher_text = launcher_text.replace("\\", "/")
        except OSError:
            pass
    normalized_upper = launcher_text.upper()
    target_lines = [
        line
        for line in launcher_text.splitlines()
        if "@openai/codex/bin/codex.js" in line
    ]
    standard_cmd = (
        launcher_name == "codex.cmd"
        and "@ECHO OFF" in normalized_upper
        and "SETLOCAL" in normalized_upper
        and any(
            '"%_PROG%"' in line.upper()
            and "%DP0%" in line.upper()
            and "%*" in line
            for line in target_lines
        )
    )
    standard_powershell = launcher_name == "codex.ps1" and any(
        "&" in line and "$basedir" in line and "$args" in line
        for line in target_lines
    )
    if (
        "@openai/codex/bin/codex.js" in launcher_text
        and (standard_cmd or standard_powershell)
    ):
        recognized_launcher = True
        package_roots.append(lexical.parent / "node_modules" / "@openai" / "codex")
        if lexical.parent.name == ".bin":
            package_roots.append(lexical.parent.parent / "@openai" / "codex")
    if not recognized_launcher:
        return None
    package_root = None
    package_metadata: dict[str, Any] | None = None
    for candidate in package_roots:
        try:
            metadata = json.loads((candidate / "package.json").read_text())
        except (OSError, ValueError):
            continue
        if metadata.get("name") == "@openai/codex":
            package_root = candidate.resolve()
            package_metadata = metadata
            break
    if package_root is None:
        raise CapabilityError(
            f"official Codex launcher {str(lexical)!r} has no readable package metadata"
        )
    assert package_metadata is not None
    canonical_entrypoint = package_root / "bin" / "codex.js"
    try:
        with canonical_entrypoint.open("rb") as handle:
            entrypoint_text = handle.read(65536).decode(errors="replace")
    except OSError as exc:
        raise CapabilityError(
            f"official Codex launcher package has no readable bin/codex.js: {exc}"
        ) from exc
    expected_bin = package_metadata.get("bin")
    standard_entrypoint = (
        isinstance(expected_bin, Mapping)
        and expected_bin.get("codex") == "bin/codex.js"
        and all(
            marker in entrypoint_text
            for marker in (
                "PLATFORM_PACKAGE_BY_TARGET",
                "findCodexExecutable",
                "spawn(binaryPath",
                "process.argv.slice(2)",
            )
        )
    )
    if not standard_entrypoint:
        raise CapabilityError(
            "the @openai/codex launcher was customized; configure the native "
            "Codex executable directly so app-server disposal can be verified"
        )

    platform_key = platform_name or sys.platform
    architecture = (machine or platform.machine()).lower()
    architecture = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "arm64": "aarch64",
    }.get(architecture, architecture)
    package = _CODEX_PLATFORM_PACKAGES.get((platform_key, architecture))
    if package is None:
        raise CapabilityError(
            f"official Codex launcher does not support {platform_key}/{architecture}"
        )
    package_name, target, executable = package
    roots = [
        package_root / "node_modules" / "@openai" / package_name,
        package_root.parent / package_name,
        package_root,
    ]
    for root in roots:
        binary = root / "vendor" / target / "bin" / executable
        if binary.is_file():
            return binary.resolve()
    raise CapabilityError(
        f"official Codex launcher {str(lexical)!r} is missing its native "
        f"{platform_key}/{architecture} binary"
    )


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
    checkpoint_error: BaseException | None = None
    process: subprocess.Popen[bytes] | None = None


def _plain(value: Any, *, label: str) -> Any:
    try:
        encoded = json.dumps(value, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError, RecursionError) as exc:
        raise TypeError(f"{label} must be plain JSON") from exc


def _profile_hash(request: Any, config: Mapping[str, Any]) -> str:
    # Only values applied while starting/resuming the thread belong here.
    # Preset, sandboxPolicy, effort and outputSchema are applied per turn and
    # must not force a reload that would reap a yielded background terminal.
    value = {
        "workspace": str(Path(request.workspace).resolve()),
        "model": getattr(request.policy, "model", None),
        "instructions": request.instructions,
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
    feature_values = {name: False for name in known_features & _TOOL_ENABLING_FEATURES}
    for tool in tools:
        family = tool.split(":", 1)[0]
        for feature in _TOOL_FEATURES.get(family, ()):
            if feature in known_features:
                feature_values[feature] = True
    config.update(
        {f"features.{name}": enabled for name, enabled in feature_values.items()}
    )
    config["web_search"] = "live" if "web_search" in tools else "disabled"
    config["tools.experimental_request_user_input.enabled"] = (
        "request_user_input" in tools
    )
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
    """One Codex app-server process owned by a logical Botpipe operation."""

    name = "codex"

    def __init__(
        self,
        command: str | os.PathLike[str] | Sequence[str] = "codex",
        *,
        env: Mapping[str, str] | None = None,
        state_dir: Path | None = None,
        interrupt_grace_seconds: float = 10.0,
        capabilities: CodexCapabilities | None = None,
        capability_probe_stat: tuple[str, int, int] | None = None,
    ) -> None:
        self.env = {str(key): str(value) for key, value in (env or {}).items()}
        effective_path = self.env.get("PATH", os.environ.get("PATH"))
        self.command: tuple[str, ...]
        if isinstance(command, (str, os.PathLike)):
            executable = str(
                _packaged_codex_binary(command, search_path=effective_path) or command
            )
            self.command = (executable, "app-server", "--listen", "stdio://")
        else:
            self.command = tuple(map(str, command))
            if not self.command:
                raise ValueError("Codex command cannot be empty")
            executable = str(
                _packaged_codex_binary(
                    self.command[0], search_path=effective_path
                )
                or self.command[0]
            )
            if executable != self.command[0]:
                self.command = (executable, *self.command[1:])
        self.executable = executable
        self.state_dir = state_dir
        self.interrupt_grace_seconds = float(interrupt_grace_seconds)
        self._capabilities = capabilities
        self._injected_capabilities = (
            capabilities is not None and capability_probe_stat is None
        )
        self._probe_stat = capability_probe_stat
        self._process: subprocess.Popen[bytes] | None = None
        self._containment: ProcessContainment | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr: list[bytes] = []
        self._lock = threading.RLock()
        # Process installation and teardown share one reentrant lifecycle lock.
        # Reentrancy lets initialization failure clean up the process installed
        # by the same _start call without exposing a replacement in between.
        self._transport_cleanup_lock = threading.RLock()
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
        self._tearing_down_process: subprocess.Popen[bytes] | None = None
        self._disposing_process: subprocess.Popen[bytes] | None = None
        self._transport_cleanup_results: weakref.WeakKeyDictionary[
            subprocess.Popen[bytes], str | None
        ] = weakref.WeakKeyDictionary()
        self._cleanup_checkpoint_failures: weakref.WeakSet[
            subprocess.Popen[bytes]
        ] = weakref.WeakSet()
        self._pre_exit_captured: weakref.WeakSet[subprocess.Popen[bytes]] = (
            weakref.WeakSet()
        )
        self._active_calls = 0
        self._closed = False
        self._cleanup_complete = False

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
        if not self._transport_cleanup_lock.acquire(timeout=lock_timeout):
            raise TimeoutError("Codex initialization timed out")
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Codex adapter is closed")
                if self._process is not None and self._process.poll() is None:
                    return
                if self._process is not None:
                    previous_process = self._process
                    try:
                        self._kill_transport(
                            CodexProtocolError("previous app-server process exited"),
                            expected_process=previous_process,
                        )
                    except CodexProtocolError:
                        # The owning ledger already retains this
                        # conservative cleanup failure. It must not permanently
                        # prevent unrelated work from installing a replacement.
                        recorded = self._transport_cleanup_results.get(
                            previous_process, _CLOSED
                        )
                        if (
                            recorded is _CLOSED
                            or recorded is None
                            or previous_process in self._cleanup_checkpoint_failures
                        ):
                            raise
                capabilities = self.probe(deadline=deadline)
                if self._containment is not None:
                    self._containment.close()
                    self._containment = None
                self._tearing_down_process = None
                self._orphan_events.clear()
                self._thread_profiles.clear()
                # Old waiters retain their _Turn objects and cleanup audit,
                # but events from the replacement transport must not bind
                # to those stale registrations.
                self._turns.clear()
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
                if (
                    os.name == "nt"
                    and "windowsSandbox/readiness" in capabilities.methods
                ):
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
            self._transport_cleanup_lock.release()

    def _read_stderr(self, process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        try:
            for chunk in self._pipe_chunks(process.stderr, process):
                self._stderr.append(chunk[-8192:])
                if len(self._stderr) > 32:
                    del self._stderr[:-32]
        finally:
            process.stderr.close()

    @staticmethod
    def _pipe_chunks(pipe: Any, process: subprocess.Popen[bytes]):
        """Read a pipe without waiting forever on handles inherited by children."""

        descriptor = pipe.fileno()
        os.set_blocking(descriptor, False)
        exit_deadline: float | None = None
        while True:
            if process.poll() is not None and exit_deadline is None:
                # Drain bytes already queued by the parent, but bound the drain
                # if a surviving descendant continuously writes the same pipe.
                exit_deadline = time.monotonic() + 0.05
            try:
                chunk = os.read(descriptor, 64 * 1024)
            except BlockingIOError:
                if exit_deadline is not None:
                    return
                time.sleep(0.01)
                continue
            except OSError:
                if process.poll() is not None:
                    return
                raise
            if not chunk:
                return
            yield chunk
            if exit_deadline is not None and time.monotonic() >= exit_deadline:
                return

    def _read_loop(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        failure: BaseException | None = None
        try:
            buffered = bytearray()

            def receive_raw(raw: bytes) -> None:
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
                self._receive(dict(message), process=process)

            for chunk in self._pipe_chunks(process.stdout, process):
                buffered.extend(chunk)
                if len(buffered) > 8 * 1024 * 1024 and b"\n" not in buffered:
                    raise CodexProtocolError("app-server message exceeds 8 MiB")
                while True:
                    newline = buffered.find(b"\n")
                    if newline < 0:
                        break
                    raw = bytes(buffered[: newline + 1])
                    del buffered[: newline + 1]
                    receive_raw(raw)
            if buffered:
                # Match BufferedReader.readline at EOF: a complete JSON value
                # needs no final newline, while truncated data is an error.
                receive_raw(bytes(buffered))
        except BaseException as exc:  # noqa: BLE001 - reader must wake waiters on every exit
            failure = exc
        finally:
            process.stdout.close()
        if failure is None:
            detail = b"".join(self._stderr).decode(errors="replace").strip()
            failure = CodexProtocolError(
                "app-server closed" + (f": {detail[-2000:]}" if detail else "")
            )
        with self._lock:
            disposing = self._disposing_process is process
        if disposing:
            # Normal disposal owns this EOF.  In particular, do not turn it into
            # the process-tree cleanup used for cancellation and transport loss.
            self._fail_transport(failure, process=process)
            return
        try:
            self._kill_transport(failure, expected_process=process)
        except BaseException as cleanup_error:  # reader must always wake old waiters
            self._fail_transport(cleanup_error, process=process)

    def _receive(
        self,
        message: dict[str, Any],
        *,
        process: subprocess.Popen[bytes] | None = None,
    ) -> None:
        request_id = message.get("id")
        if request_id is not None and "method" not in message:
            with self._lock:
                pending = (
                    self._pending.get(request_id)
                    if process is None or self._process is process
                    else None
                )
            if pending is not None:
                try:
                    pending.put_nowait(message)
                except queue.Full:
                    pass
            return
        method = message.get("method")
        if isinstance(method, str) and request_id is not None:
            with self._lock:
                if process is not None and self._process is not process:
                    return
            self._answer_server_request(request_id, method, process=process)
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
            if process is not None and self._process is not process:
                return
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
            if turn is None and isinstance(turn_id, str):
                if (
                    len(self._orphan_events) >= 256
                    and (thread_id, turn_id) not in self._orphan_events
                ):
                    self._orphan_events.pop(next(iter(self._orphan_events)))
                events = self._orphan_events.setdefault((thread_id, turn_id), [])
                if len(events) < 128:
                    events.append((method, dict(params)))
        if turn is None:
            return
        self._record_event(turn, method, dict(params))

    def _answer_server_request(
        self,
        request_id: Any,
        method: str,
        *,
        process: subprocess.Popen[bytes] | None = None,
    ) -> None:
        if method == "mcpServer/elicitation/request":
            response: dict[str, Any] = {
                "id": request_id,
                "result": {"action": "decline"},
            }
        elif method in {"applyPatchApproval", "execCommandApproval"}:
            response = {"id": request_id, "result": {"decision": "abort"}}
        elif method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            response = {"id": request_id, "result": {"decision": "cancel"}}
        elif method in _APPROVAL_REQUESTS:
            response = {
                "id": request_id,
                "error": {
                    "code": -32001,
                    "message": "Botpipe approval policy is never",
                },
            }
        else:
            response = {
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Botpipe does not mediate {method}",
                },
            }
        self._send(response, process=process)

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
                        update: dict[str, Any] = {
                            "status": (
                                "response_received"
                                if status in (None, "completed")
                                else "turn_terminal"
                            ),
                            "native_status": status,
                            "session_id": turn.thread_id,
                            "turn_id": turn.turn_id,
                            "audit": list(turn.events),
                        }
                        if turn.messages:
                            update["response"] = {
                                "text": turn.messages[-1],
                                "session_id": turn.thread_id,
                                "usage": dict(turn.usage),
                                "metadata": {
                                    "provider": "codex",
                                    "thread_id": turn.thread_id,
                                    "turn_id": turn.turn_id,
                                    "audit": list(turn.events),
                                },
                            }
                        turn.on_checkpoint(update)
                    except Exception as exc:
                        # Terminal response evidence is a durability boundary.
                        # A failed callback must wake the caller and prevent it
                        # from treating the native completion as accepted.
                        turn.checkpoint_error = exc
                        turn.error = CodexProtocolError(
                            f"terminal response checkpoint failed: {exc}"
                        )
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

    def _send(
        self,
        message: Mapping[str, Any],
        *,
        process: subprocess.Popen[bytes] | None = None,
    ) -> None:
        payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        with self._write_lock:
            current = self._process
            if process is not None and current is not process:
                raise CodexProtocolError("app-server transport was replaced")
            process = current
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
        process: subprocess.Popen[bytes] | None = None,
    ) -> dict[str, Any]:
        response_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            self._pending[request_id] = response_queue
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Codex RPC {method} timed out before dispatch")
            self._send(
                {"id": request_id, "method": method, "params": params},
                process=process,
            )
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
        with self._lock:
            if self._closed:
                raise RuntimeError("Codex adapter is closed")
            self._active_calls += 1
        try:
            return self._start_turn(request, on_event)
        finally:
            with self._lock:
                self._active_calls -= 1

    def _start_turn(
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
                if sandbox_name == "danger-full-access"
                or sandbox_policy.get("networkAccess")
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
                    refresh_loaded = (
                        previous_profile is not None
                        and previous_profile != profile_hash
                    )
                    if (
                        refresh_loaded
                        and "thread/unsubscribe" in capabilities.methods
                    ):
                        # A loaded thread needs resubscription only when its
                        # thread-level configuration changed.
                        self._rpc(
                            "thread/unsubscribe",
                            {"threadId": thread_id},
                            remaining(10),
                            deadline=deadline,
                        )
                    elif (
                        refresh_loaded
                        and "thread/unsubscribe" not in capabilities.methods
                    ):
                        raise CapabilityError(
                            "thread/unsubscribe is required to change a loaded "
                            "thread's configuration"
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
                dispatch_process = self._process
                dispatch_reader = self._reader
            acknowledged_turn_id: str | None = None
            turn: _Turn | None = None
            turn_registered = False
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
                    process=dispatch_process,
                )
                turn_value = started.get("turn")
                turn_id = (
                    turn_value.get("id") if isinstance(turn_value, Mapping) else None
                )
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexProtocolError("turn/start returned no turn id")
                acknowledged_turn_id = turn_id
                turn = _Turn(
                    thread_id,
                    turn_id,
                    request.tools,
                    on_event or request.on_event,
                    request.on_checkpoint,
                    process=dispatch_process,
                )
                # Bind the ACK and turn registration to the exact transport
                # that accepted turn/start. Teardown marks that process while
                # holding _lock, and takes its affected-turn snapshot under the
                # same lock, so registration either precedes the snapshot or
                # is rejected after cleanup began.
                with self._lock:
                    if (
                        dispatch_process is None
                        or self._process is not dispatch_process
                        or self._tearing_down_process is dispatch_process
                        or dispatch_process.poll() is not None
                    ):
                        raise CodexProtocolError(
                            "turn/start acknowledgement belonged to a stopped transport"
                        )
                    self._turns[(thread_id, turn_id)] = turn
                    turn_registered = True
                    early = self._orphan_events.pop((thread_id, turn_id), ())
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
                # The native acknowledgement is the durable identity boundary.
                # Only publish buffered notifications after it, even when Codex
                # emitted a complete response before the turn/start RPC reply.
                for method, event_params in early:
                    self._record_event(turn, method, event_params)
            except BaseException as exc:
                try:
                    self._kill_transport(
                        CodexTurnError("turn/start acknowledgement was not durable"),
                        grace_seconds=0.1,
                        expected_process=dispatch_process,
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
                reader = dispatch_reader
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
                if turn_registered:
                    assert turn is not None
                    with self._lock:
                        key = (thread_id, turn.turn_id)
                        if self._turns.get(key) is turn:
                            self._turns.pop(key)
                    pre_ack = turn
                    recovered_single_turn = True
                else:
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
                    recovered_single_turn = len(orphaned) == 1
                    if recovered_single_turn:
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
                    recovered_single_turn
                    and pre_ack.completed
                    and pre_ack.error is None
                    and pre_ack.messages
                ):
                    from .providers import ProviderResponse

                    response = ProviderResponse(
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
                        request.on_checkpoint(
                            {
                                "status": "response_received",
                                "session_id": thread_id,
                                "turn_id": pre_ack.turn_id,
                                "enforcement": enforcement,
                                "audit": list(pre_ack.events),
                                "response": response.to_record(),
                            }
                        )
                    return response
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
            assert turn is not None and turn_registered
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
                    if (
                        request.on_checkpoint is not None
                        and turn.checkpoint_error is None
                    ):
                        request.on_checkpoint(
                            {"enforcement": enforcement, "audit": list(turn.events)}
                        )
                finally:
                    with self._lock:
                        key = (thread_id, turn_id)
                        if self._turns.get(key) is turn:
                            self._turns.pop(key)

    def recover_turn(
        self, request: Any, *, thread_id: str, turn_id: str
    ) -> tuple[str, Any | None]:
        with self._lock:
            if self._closed:
                raise RuntimeError("Codex adapter is closed")
            self._active_calls += 1
        try:
            return self._recover_turn(request, thread_id=thread_id, turn_id=turn_id)
        finally:
            with self._lock:
                self._active_calls -= 1

    def _recover_turn(
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
        checkpoint = request.checkpoint if isinstance(request.checkpoint, Mapping) else {}
        recorded_profile = checkpoint.get("profile_hash")
        profile_hash = (
            recorded_profile
            if isinstance(recorded_profile, str) and recorded_profile
            else _profile_hash(request, config)
        )
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
        if request.instructions:
            common["developerInstructions"] = request.instructions

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
        cleanup_required = False
        recovered: _Turn | None = None
        try:
            previous_profile = self._thread_profiles.get(thread_id)
            refresh_loaded = (
                previous_profile is not None and previous_profile != profile_hash
            )
            if refresh_loaded and "thread/unsubscribe" in capabilities.methods:
                self._rpc(
                    "thread/unsubscribe",
                    {"threadId": thread_id},
                    remaining(10),
                    deadline=deadline,
                )
            elif refresh_loaded:
                raise CapabilityError(
                    "thread/unsubscribe is required to change a loaded thread's "
                    "configuration"
                )
            self._rpc("thread/resume", common, remaining(10), deadline=deadline)
            self._thread_profiles[thread_id] = profile_hash
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
            if isinstance(match, Mapping) and status in {
                "completed",
                "failed",
                "interrupted",
                "cancelled",
            }:
                recovered = _Turn(thread_id, turn_id, request.tools, None)
                for item in match.get("items", ()):
                    if isinstance(item, Mapping):
                        self._record_event(
                            recovered,
                            "item/completed",
                            {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "item": dict(item),
                            },
                        )
            cleanup_required = status in {"failed", "interrupted", "cancelled"} or (
                recovered is not None
                and isinstance(recovered.error, CapabilityError)
            )
            if cleanup_required:
                cleanup_methods = {
                    "thread/backgroundTerminals/clean",
                    "thread/backgroundTerminals/list",
                }
                if request.cancel_event is not None and request.cancel_event.is_set():
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
        assert recovered is not None
        enforcement = dict(checkpoint.get("enforcement") or {})
        enforcement["audit"] = (
            "tool-policy-violation"
            if isinstance(recovered.error, CapabilityError)
            else "tool-calls-observed"
            if recovered.tools_observed
            else "no-tool-calls-observed"
        )
        evidence = {"enforcement": enforcement, "audit": recovered.events}
        if cleanup_required:
            evidence["cleanup"] = (
                {"status": "completed"}
                if cleanup_uncertain is None
                else {
                    "status": "incomplete",
                    "error": cleanup_uncertain,
                }
            )
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
                "codex_version": enforcement.get("codex_version", capabilities.version),
                "thread_id": thread_id,
                "turn_id": turn_id,
                "recovered": True,
                **evidence,
            },
        )

    def interrupt(
        self,
        thread_id: str,
        turn_id: str,
        *,
        process: subprocess.Popen[bytes] | None = None,
    ) -> None:
        self._rpc(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            min(5.0, self.interrupt_grace_seconds),
            process=process,
        )

    def _stop_turn(self, turn: _Turn, reason: str) -> None:
        with self._lock:
            process = turn.process
            containment = self._containment if self._process is process else None
        if process is not None and containment is not None:
            containment.capture_descendant_groups(process)
            if process.poll() is None:
                self._pre_exit_captured.add(process)
        cleanup_deadline = time.monotonic() + self.interrupt_grace_seconds
        try:
            self.interrupt(turn.thread_id, turn.turn_id, process=process)
        except Exception:  # noqa: BLE001,S110 - escalation below is authoritative
            pass
        # Codex deliberately keeps background terminals alive after interruption.
        # Give its native cleanup the grace period, including after turn/completed.
        self._kill_transport(
            CodexTurnError(reason),
            grace_seconds=0.1,
            cleanup_seconds=max(0.0, cleanup_deadline - time.monotonic()),
            expected_process=process,
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
                # A terminal notification is authoritative even if transport
                # teardown follows it immediately.
                if not turn.completed and turn.error is None:
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
        expected_process: subprocess.Popen[bytes] | None = None,
        retry_incomplete: bool = False,
    ) -> None:
        # Stopping a turn stops its session app-server because Codex can keep
        # background terminals alive after turn interruption.  Serialize that
        # containment boundary so every affected caller returns only after the
        # same process tree has been verified quiescent.
        with self._transport_cleanup_lock:
            process, containment = self._process, self._containment
            if process is not None:
                current_cleanup = self._transport_cleanup_results.get(process, _CLOSED)
            else:
                current_cleanup = _CLOSED
            if expected_process is process:
                prior_cleanup = current_cleanup
            elif expected_process is not None:
                prior_cleanup = self._transport_cleanup_results.get(
                    expected_process, _CLOSED
                )
            else:
                prior_cleanup = current_cleanup
            if expected_process is not None and process is not expected_process:
                if prior_cleanup is _CLOSED:
                    raise CodexProtocolError(
                        "cleanup of the replaced app-server transport was not verified"
                    )
                if prior_cleanup is not None:
                    raise CodexProtocolError(prior_cleanup)
                return
            retry_recorded_failure = retry_incomplete and prior_cleanup not in (
                _CLOSED,
                None,
            )
            if prior_cleanup is not _CLOSED and not retry_recorded_failure:
                if prior_cleanup is not None:
                    raise CodexProtocolError(prior_cleanup)
                return
            with self._lock:
                self._tearing_down_process = process
            try:
                parent_alive_at_entry = process is not None and process.poll() is None
                cleanup_started_after_parent_exit = (
                    os.name == "posix"
                    and process is not None
                    and not parent_alive_at_entry
                    and process not in self._pre_exit_captured
                )
                if process is not None and containment is not None:
                    containment.capture_descendant_groups(process)
                    if parent_alive_at_entry:
                        self._pre_exit_captured.add(process)
                if process is not None and process.poll() is None:
                    deadline = time.monotonic() + cleanup_seconds
                    if (
                        self._capabilities is not None
                        and "thread/backgroundTerminals/clean"
                        in self._capabilities.methods
                    ):
                        with self._lock:
                            threads = set(self._thread_profiles) | {
                                thread_id for thread_id, _ in self._turns
                            }
                            requests = [
                                (
                                    "turn/interrupt",
                                    {"threadId": tid, "turnId": turn_id},
                                )
                                for (tid, turn_id), turn in self._turns.items()
                                if not turn.completed
                            ]
                        requests.extend(
                            (
                                "thread/backgroundTerminals/clean",
                                {"threadId": thread_id},
                            )
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
                cleanup_errors: list[BaseException] = []
                if cleanup_started_after_parent_exit:
                    cleanup_errors.append(
                        CodexProtocolError(
                            "process-tree cleanup began after the app-server exited; "
                            "detached descendants cannot be verified"
                        )
                    )
                if process is not None and containment is not None:
                    if process.poll() is None:
                        try:
                            containment.terminate(process, grace_seconds=grace_seconds)
                        except BaseException as exc:  # cleanup still continues below
                            cleanup_errors.append(exc)
                    try:
                        containment.ensure_tree_exited(
                            process, grace_seconds=grace_seconds
                        )
                    except BaseException as exc:
                        cleanup_errors.append(exc)
                with self._lock:
                    affected_turns = [
                        turn
                        for turn in self._turns.values()
                        if not turn.completed
                        or isinstance(turn.error, CapabilityError)
                    ]
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
                    if process is not None:
                        self._transport_cleanup_results[process] = str(failure)
                    if process is not None and checkpoint_errors:
                        self._cleanup_checkpoint_failures.add(process)
                    self._fail_transport(failure, process=process)
                    raise failure
                if process is not None:
                    self._transport_cleanup_results[process] = None
                checkpoint_errors = []
                for turn in affected_turns:
                    if turn.on_checkpoint is None:
                        continue
                    try:
                        turn.on_checkpoint({"cleanup": {"status": "completed"}})
                    except BaseException as exc:
                        checkpoint_errors.append(exc)
                if checkpoint_errors:
                    failure = CodexProtocolError(
                        "app-server process-tree cleanup completed but its checkpoint failed: "
                        + "; ".join(str(exc) for exc in checkpoint_errors)
                    )
                    if process is not None:
                        # The process tree is clean, but close is not complete
                        # until the owning ledger accepts that evidence. Retain
                        # the transport so a later close retries the callback.
                        self._transport_cleanup_results[process] = str(failure)
                        self._cleanup_checkpoint_failures.add(process)
                    self._fail_transport(failure, process=process)
                    raise failure
                if process is not None:
                    self._cleanup_checkpoint_failures.discard(process)
                # Wake RPC and turn waiters only after containment and its
                # checkpoints are durable; returning is the quiescence boundary.
                self._fail_transport(error, process=process)
            finally:
                # Keep the old process marked until _start installs a new one;
                # its reader may observe EOF after containment has completed.
                with self._lock:
                    if self._process is process:
                        self._tearing_down_process = process

    def close(self) -> None:
        with self._transport_cleanup_lock:
            with self._lock:
                if self._cleanup_complete:
                    return
                self._closed = True
            cleanup_error: BaseException | None = None
            try:
                self._kill_transport(
                    CodexProtocolError("Codex adapter closed"),
                    retry_incomplete=True,
                )
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
            if cleanup_error is not None:
                raise cleanup_error
            if containment is not None:
                containment.close()
            with self._lock:
                self._cleanup_complete = True

    def dispose(self) -> None:
        """Exit an idle app-server and relinquish it without tree cleanup."""

        with self._transport_cleanup_lock:
            with self._lock:
                if self._cleanup_complete:
                    return
                active_turns = [
                    turn for turn in self._turns.values() if not turn.completed
                ]
                if self._active_calls or active_turns or self._pending:
                    raise RuntimeError(
                        "cannot dispose a Codex adapter with active work"
                    )
                self._closed = True
                process, containment = self._process, self._containment
                self._disposing_process = process
            if process is None:
                if containment is not None:
                    containment.close()
                with self._lock:
                    self._containment = None
                    self._cleanup_complete = True
                return
            if containment is None:
                raise CodexProtocolError(
                    "cannot dispose app-server without process containment ownership"
                )
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            # Current native app-servers do not exit on stdio EOF.  The idle
            # parent receives SIGINT/TerminateProcess; descendants are neither
            # inspected nor signalled by this path.
            containment.release(process, grace_seconds=1.0)
            with self._lock:
                if self._process is process:
                    self._process = None
                    self._containment = None
                self._cleanup_complete = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "CodexAppServerAdapter",
    "CodexProtocolError",
    "CodexTurnError",
]
