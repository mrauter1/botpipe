"""Pinned Pi SDK adapter using Botpipe's interactive tool mediator."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .native_tools import (
    ExactCommandTools,
    ReadOnlyTools,
    ToolObservation,
    command_scope_is_workspace_wide,
)
from .policy import OperationKind
from .providers import (
    PI_SDK_CAPABILITIES,
    CapabilityError,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
    _CLIProvider,
    _NATIVE_EVENT_SINK,
    _ProviderTimedOut,
    _validate_pi_unrestricted_policy,
)
from .recovery import RecoveryOutcome
from .tool_evidence import ToolEvidence, ToolEvidenceError


PROTOCOL = "botpipe.pi-sdk.v1"
TOOL_CALL_LIMIT = 16
TOOL_OUTPUT_BYTES = 32_000
RAW_CAPTURE_BYTES = 4 * 1024 * 1024


@dataclass(slots=True)
class _Mediation:
    start: dict[str, Any]
    reads: ReadOnlyTools | None
    commands: ExactCommandTools | None
    observations: list[ToolObservation]
    evidence: ToolEvidence
    terminal: dict[str, Any] | None = None
    raw_truncated: bool = False

    def close(self) -> None:
        if self.reads is not None:
            self.reads.close()
        if self.commands is not None:
            self.commands.close()


class PiSDKProvider(_CLIProvider):
    """Pinned Pi SDK profile for mediated planning and unrestricted run."""

    name = "pi"
    capabilities = PI_SDK_CAPABILITIES

    def __init__(
        self,
        *,
        node_command: str | tuple[str, ...] = ("node",),
        bridge_path: str | Path | None = None,
        sdk_root: str | Path | None = None,
        model_provider: str = "anthropic",
        env: Mapping[str, str] | None = None,
    ) -> None:
        node = (node_command,) if isinstance(node_command, str) else tuple(node_command)
        if not node:
            raise ValueError("node_command cannot be empty")
        bridge = (
            Path(bridge_path)
            if bridge_path is not None
            else Path(__file__).with_name("pi_sdk_bridge.mjs")
        ).resolve(strict=True)
        merged_env = {str(key): str(value) for key, value in (env or {}).items()}
        if sdk_root is not None:
            merged_env["BOTPIPE_PI_SDK_ROOT"] = str(Path(sdk_root).resolve(strict=True))
        super().__init__((*node, str(bridge)), env=merged_env)
        if type(model_provider) is not str or not model_provider:
            raise ValueError("model_provider must be a non-empty string")
        self.model_provider = model_provider
        self._mediations_lock = threading.Lock()
        self._mediations: dict[tuple[str, int], _Mediation] = {}

    def validate_request(self, request: ProviderRequest) -> None:
        super().validate_request(request)
        if request.operation is OperationKind.RUN:
            _validate_pi_unrestricted_policy(request.policy.effective())
        if request.policy.effective().model is None:
            raise CapabilityError("Pi SDK profile requires an explicit policy model")

    def run(self, request: ProviderRequest) -> ProviderResponse:
        self.validate_request(request)
        key = (request.operation_id, request.attempt)
        try:
            return super().run(request)
        finally:
            with self._mediations_lock:
                mediation = self._mediations.pop(key, None)
            if mediation is not None:
                mediation.close()

    def cancel(self, operation_id: str) -> RecoveryOutcome:
        return super().cancel(operation_id)

    def _build(self, request: ProviderRequest, policy):
        roots = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.allow_read or ())
        )
        excluded = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.deny_read or ())
        )
        reads = None
        commands = None
        if request.operation is OperationKind.QUERY:
            reads = ReadOnlyTools(
                roots,
                exclusions=excluded,
                max_output_bytes=TOOL_OUTPUT_BYTES,
                read_fence=request.read_fence,
            )
        elif request.allow_commands:
            if not command_scope_is_workspace_wide(
                request.workspace, policy.allow_read, policy.deny_read
            ):
                raise CapabilityError(
                    "exact command grants require workspace-wide allow_read and no deny_read paths"
                )
            commands = ExactCommandTools(
                request.workspace,
                request.allow_commands,
                max_output_bytes=TOOL_OUTPUT_BYTES,
            )
        effort = policy.effort.value if policy.effort is not None else "off"
        start = {
            "type": "start",
            "protocol": PROTOCOL,
            "operation_id": request.operation_id,
            "operation": request.operation.value,
            "prompt": request.prompt,
            "system_prompt": request.instructions or "You are a Botpipe provider.",
            "cwd": str(request.workspace.resolve()),
            "model": {"provider": self.model_provider, "id": policy.model},
            "thinking_level": effort,
            "grant_ids": list(commands.envelopes) if commands is not None else [],
        }
        if request.operation is OperationKind.RUN:
            start["run_profile"] = "danger-full-access-network-full-unrestricted"
        if request.output_schema is not None:
            start["output_schema"] = request.output_schema
        if request.session_id is None:
            start["session_dir"] = str(
                (request.receipt_dir / "pi-sessions").resolve()
            )
        else:
            session_file = Path(request.session_id)
            if not session_file.is_absolute():
                raise CapabilityError("Pi session_id must be an absolute session file")
            try:
                session_file = session_file.resolve(strict=True)
            except OSError as exc:
                raise CapabilityError("Pi session file is unavailable") from exc
            if not session_file.is_file() or session_file.is_symlink():
                raise CapabilityError("Pi session file must be a regular non-symlink file")
            start["session_file"] = str(session_file)
        evidence = ToolEvidence(
            request,
            self.capabilities.version,
            max_observations=TOOL_CALL_LIMIT,
            max_bytes=1_000_000,
        )
        try:
            envelopes = []
            if reads is not None:
                envelopes.extend(reads.command_envelopes.values())
            if commands is not None:
                envelopes.extend(commands.envelopes.values())
            evidence.prepare(envelopes)
        except BaseException:
            if reads is not None:
                reads.close()
            if commands is not None:
                commands.close()
            raise
        mediation = _Mediation(start, reads, commands, [], evidence)
        key = (request.operation_id, request.attempt)
        with self._mediations_lock:
            if key in self._mediations:
                mediation.close()
                raise ProviderInterruptedError(
                    f"Pi SDK mediation already exists for {request.operation_id!r}"
                )
            self._mediations[key] = mediation
        return list(self.command), dict(self.env), {
            "native_interface": "agent_sdk",
            "protocol": PROTOCOL,
            "model_provider": self.model_provider,
            "tool_inventory": (
                []
                if request.operation is OperationKind.GENERATE and commands is None
                else ["run_exact_command"]
                if request.operation is OperationKind.GENERATE
                else ["read", "bash", "edit", "write", "grep", "find", "ls"]
                if request.operation is OperationKind.RUN
                else ["read_file", "list_files", "search_text", "count_lines"]
            ),
        }

    def _stdin(self, request: ProviderRequest) -> bytes:
        return b""

    def _communicate(
        self,
        process: subprocess.Popen[bytes],
        prompt: bytes,
        timeout: float,
        *,
        receipt: Path,
        started: dict[str, Any],
    ) -> tuple[bytes, bytes]:
        del prompt
        key = (started["operation_id"], started["attempt"])
        with self._mediations_lock:
            mediation = self._mediations.get(key)
        if mediation is None:
            raise ProviderError("Pi SDK mediation state is missing")
        lines: queue.Queue[bytes | None] = queue.Queue(maxsize=4)
        stderr_parts: list[bytes] = []
        reader_errors: list[BaseException] = []
        captured = bytearray()
        sink = _NATIVE_EVENT_SINK.get()
        stop_readers = threading.Event()

        def put_line(value: bytes | None) -> bool:
            while not stop_readers.is_set():
                try:
                    lines.put(value, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def stdout_reader() -> None:
            try:
                assert process.stdout is not None
                while not stop_readers.is_set():
                    line = process.stdout.readline(RAW_CAPTURE_BYTES + 1)
                    if not line:
                        break
                    if len(line) > RAW_CAPTURE_BYTES or not line.endswith(b"\n"):
                        raise ProviderError(
                            "Pi SDK bridge emitted an overlong protocol line"
                        )
                    if not put_line(line):
                        return
            except BaseException as exc:
                reader_errors.append(exc)
            finally:
                put_line(None)

        def stderr_reader() -> None:
            try:
                assert process.stderr is not None
                retained = 0
                for chunk in iter(lambda: process.stderr.read(64 * 1024), b""):
                    remaining = RAW_CAPTURE_BYTES - retained
                    if remaining > 0:
                        stderr_parts.append(chunk[:remaining])
                        retained += min(len(chunk), remaining)
            except BaseException as exc:
                reader_errors.append(exc)

        threads = [
            threading.Thread(target=stdout_reader, daemon=True),
            threading.Thread(target=stderr_reader, daemon=True),
        ]
        for thread in threads:
            thread.start()
        assert process.stdin is not None
        process.stdin.write((json.dumps(mediation.start) + "\n").encode())
        process.stdin.flush()
        deadline = time.monotonic() + timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                try:
                    line = lines.get(timeout=remaining)
                except queue.Empty:
                    self._stop(process)
                    for thread in threads:
                        thread.join(1.0)
                    raise _ProviderTimedOut(
                        self.command,
                        timeout,
                        output=bytes(captured),
                        stderr=b"".join(stderr_parts),
                    )
                if line is None:
                    break
                remaining_capture = RAW_CAPTURE_BYTES - len(captured)
                if remaining_capture > 0:
                    captured.extend(line[:remaining_capture])
                if len(line) > remaining_capture:
                    mediation.raw_truncated = True
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ProviderError("Pi SDK bridge emitted invalid JSON") from exc
                if not isinstance(record, Mapping):
                    raise ProviderError("Pi SDK bridge emitted a non-object record")
                kind = record.get("type")
                if kind == "native_event":
                    event = record.get("event")
                    if sink is not None and isinstance(event, Mapping):
                        sink(event)
                elif kind == "tool_call":
                    response = self._tool_result(mediation, record)
                    process.stdin.write((json.dumps(response) + "\n").encode())
                    process.stdin.flush()
                elif kind == "terminal":
                    mediation.terminal = dict(record)
                elif kind == "protocol_error":
                    mediation.terminal = {
                        "status": "failed",
                        "error": record.get("error") or "Pi SDK protocol error",
                    }
            for thread in threads:
                thread.join(1.0)
            if any(thread.is_alive() for thread in threads):
                raise ProviderError("Pi SDK protocol reader did not terminate")
            if reader_errors:
                raise ProviderError(f"Pi SDK protocol reader failed: {reader_errors[0]}")
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            return bytes(captured), b"".join(stderr_parts)
        finally:
            stop_readers.set()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()

    def _tool_result(
        self, mediation: _Mediation, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        base = {
            "type": "tool_result",
            "protocol": PROTOCOL,
            "operation_id": mediation.start["operation_id"],
            "call_id": record.get("call_id"),
        }
        try:
            if record.get("protocol") != PROTOCOL or record.get(
                "operation_id"
            ) != mediation.start["operation_id"]:
                raise CapabilityError("Pi SDK tool call routing fields do not match")
            if type(record.get("call_id")) is not str or not record["call_id"]:
                raise CapabilityError("Pi SDK tool call has no call_id")
            if len(mediation.observations) >= TOOL_CALL_LIMIT:
                raise CapabilityError(
                    f"native tool call limit of {TOOL_CALL_LIMIT} was reached"
                )
            tool = record.get("tool")
            arguments = record.get("arguments")
            if not isinstance(arguments, Mapping):
                raise CapabilityError("Pi SDK tool arguments must be an object")
            if tool == "read_file" and mediation.reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = mediation.reads.read(arguments.get("path"))
            elif tool == "list_files" and mediation.reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = mediation.reads.list(arguments.get("path", "."))
            elif tool == "search_text" and mediation.reads is not None:
                self._exact_keys(arguments, {"query", "path"})
                observation = mediation.reads.search(
                    arguments.get("query"), arguments.get("path", ".")
                )
            elif tool == "count_lines" and mediation.reads is not None:
                self._exact_keys(arguments, {"path"})
                observation = mediation.reads.count_lines(arguments.get("path"))
            elif tool == "run_exact_command" and mediation.commands is not None:
                self._exact_keys(arguments, {"grant_id"})
                observation = mediation.commands.execute(arguments.get("grant_id"))
            else:
                raise CapabilityError(f"Pi SDK requested unavailable tool {tool!r}")
            try:
                mediation.evidence.record(observation)
            except ToolEvidenceError:
                # Do not send any tool result. Propagation closes stdin and the
                # base adapter terminates the owned native process tree.
                raise
            mediation.observations.append(observation)
            evidence = observation.to_record()
            return {
                **base,
                "ok": True,
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(evidence, ensure_ascii=False),
                    }
                ],
                "details": evidence,
            }
        except ToolEvidenceError:
            # Evidence durability is part of the tool result contract.  The
            # caller closes stdin and stops the native process tree rather than
            # telling the planner that an unrecorded effect merely failed.
            raise
        except BaseException as exc:
            return {**base, "ok": False, "error": str(exc)[:4096]}

    @staticmethod
    def _exact_keys(value: Mapping[str, Any], allowed: set[str]) -> None:
        unknown = set(value) - allowed
        if unknown:
            raise CapabilityError(
                "Pi SDK tool call contains unsupported fields: "
                + ", ".join(sorted(map(str, unknown)))
            )

    def _parse(self, stdout: str, request: ProviderRequest, emission: dict[str, Any]):
        del stdout
        key = (request.operation_id, request.attempt)
        with self._mediations_lock:
            mediation = self._mediations.get(key)
        if mediation is None or mediation.terminal is None:
            raise ProviderInterruptedError(
                "Pi SDK stream ended without an authoritative terminal record"
            )
        terminal = mediation.terminal
        if terminal.get("status") != "completed":
            raise ProviderError(
                f"Pi SDK terminal failure: {terminal.get('error') or terminal.get('status')}"
            )
        result = terminal.get("result")
        if not isinstance(result, str):
            raise ProviderError("Pi SDK completed without result text")
        usage = terminal.get("usage")
        if not isinstance(usage, Mapping):
            usage = {}
        locator = terminal.get("session_locator")
        if not isinstance(locator, Mapping):
            raise ProviderError("Pi SDK completed without a session locator")
        if set(locator) != {
            "provider",
            "format",
            "format_version",
            "package",
            "session_id",
            "session_file",
            "cwd",
        }:
            raise ProviderError("Pi SDK returned an invalid session locator shape")
        expected = {
            "provider": "pi",
            "format": "pi-session-jsonl",
            "format_version": 3,
            "package": "@mariozechner/pi-coding-agent@0.73.1",
            "cwd": str(request.workspace.resolve()),
        }
        if any(locator.get(name) != value for name, value in expected.items()):
            raise ProviderError("Pi SDK returned an incompatible session locator")
        native_session_id = locator.get("session_id")
        session_file = locator.get("session_file")
        if (
            type(native_session_id) is not str
            or not native_session_id
            or type(session_file) is not str
            or not session_file
            or not Path(session_file).is_absolute()
            or terminal.get("session_id") != native_session_id
        ):
            raise ProviderError("Pi SDK returned an invalid session identity")
        session_path = Path(session_file)
        if session_path.is_symlink():
            raise ProviderError("Pi SDK session file must not be a symlink")
        try:
            resolved_session = session_path.resolve(strict=True)
        except OSError as exc:
            raise ProviderError("Pi SDK session file is unavailable") from exc
        if not resolved_session.is_file() or resolved_session.is_symlink():
            raise ProviderError("Pi SDK session file must be a regular non-symlink file")
        if request.session_id is not None and resolved_session != Path(
            request.session_id
        ).resolve(strict=True):
            raise ProviderError("Pi SDK changed the resumed session identity")
        return ProviderResponse(
            result,
            str(resolved_session),
            dict(usage),
            {
                "provider": self.name,
                **emission,
                "raw_protocol_truncated": mediation.raw_truncated,
                "session_locator": dict(locator),
                "tool_observations": [
                    observation.to_record() for observation in mediation.observations
                ],
            },
        )


__all__ = ["PI_SDK_CAPABILITIES", "PROTOCOL", "PiSDKProvider"]
