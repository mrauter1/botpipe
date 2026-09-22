"""Pinned Claude Agent SDK adapter with Botpipe-owned mediated tools.

The SDK profile disables every built-in Claude Code tool and exposes only
in-process MCP tools backed by :mod:`botpipe.native_tools`.  The stock CLI
adapter remains responsible for effectful ``run`` turns.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import importlib.metadata
import json
import math
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .native_tools import (
    ExactCommandTools,
    ReadOnlyTools,
    ToolObservation,
    command_scope_is_workspace_wide,
)
from .policy import OperationKind
from .providers import (
    CapabilityError,
    ClaudeProvider,
    CLAUDE_SDK_CAPABILITIES,
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


SDK_DISTRIBUTION = "claude-agent-sdk"
SDK_VERSION = "0.2.155"
TOOL_CALL_LIMIT = 16
TOOL_OUTPUT_BYTES = 32_000
NATIVE_EVENT_BYTES = 512_000
NATIVE_EVENT_ITEMS = 1_024
NATIVE_EVENT_DEPTH = 12


class _TerminalFailure(ProviderError):
    pass


def _sdk_version() -> str:
    try:
        return importlib.metadata.version(SDK_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as exc:
        raise CapabilityError(
            f"Claude mediated operations require {SDK_DISTRIBUTION}=={SDK_VERSION}"
        ) from exc


def _plain(value: Any) -> Any:
    """Produce bounded, plain JSON event evidence from SDK message objects."""
    items = 0
    scalar_chars = 0
    active: set[int] = set()

    def visit(item: Any, depth: int) -> Any:
        nonlocal items, scalar_chars
        if depth > NATIVE_EVENT_DEPTH:
            raise ProviderError("Claude native event exceeds the nesting limit")
        items += 1
        if items > NATIVE_EVENT_ITEMS:
            raise ProviderError("Claude native event exceeds the item limit")
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ProviderError("Claude native event contains a non-finite number")
            return item
        if type(item) is str:
            scalar_chars += len(item)
            if scalar_chars > NATIVE_EVENT_BYTES:
                raise ProviderError("Claude native event exceeds the text limit")
            return item

        identity = id(item)
        if identity in active:
            raise ProviderError("Claude native event contains a reference cycle")
        active.add(identity)
        try:
            if isinstance(item, Mapping):
                return {
                    str(key): visit(child, depth + 1)
                    for key, child in item.items()
                }
            if isinstance(item, (list, tuple)):
                return [visit(child, depth + 1) for child in item]
            if dataclasses.is_dataclass(item) and not isinstance(item, type):
                return {
                    field.name: visit(getattr(item, field.name), depth + 1)
                    for field in dataclasses.fields(item)
                }
            try:
                values = vars(item)
            except TypeError:
                text = repr(item)
                scalar_chars += len(text)
                if scalar_chars > NATIVE_EVENT_BYTES:
                    raise ProviderError("Claude native event exceeds the text limit")
                return text
            return {
                str(key): visit(child, depth + 1)
                for key, child in values.items()
                if not str(key).startswith("_")
            }
        finally:
            active.remove(identity)

    result = visit(value, 0)
    try:
        encoded = json.dumps(
            result, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProviderError("Claude native event is not bounded JSON") from exc
    if len(encoded) > NATIVE_EVENT_BYTES:
        raise ProviderError("Claude native event exceeds the serialized byte limit")
    return result


def _observation_result(observation: ToolObservation) -> dict[str, Any]:
    record = observation.to_record()
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "structuredContent": record,
    }


class ClaudeSDKProvider(_CLIProvider):
    """Claude custom-tool profile pinned to one audited Agent SDK release."""

    name = "claude"
    capabilities = CLAUDE_SDK_CAPABILITIES
    supported_settings = frozenset({"max_turns"})

    def __init__(
        self,
        *,
        run_command: str | tuple[str, ...] = ("claude",),
        env: Mapping[str, str] | None = None,
    ) -> None:
        # _CLIProvider provides conservative durable recovery for the receipts
        # written below. Its command is never used for mediated turns.
        super().__init__(("claude-agent-sdk",), env=env)
        self._run_adapter = ClaudeProvider(run_command, env=env)
        self._sdk_active_lock = threading.Lock()
        self._sdk_active: dict[str, tuple[Any, Any, threading.Event]] = {}

    def validate_request(self, request: ProviderRequest) -> None:
        super().validate_request(request)
        if request.operation is OperationKind.RUN:
            self._run_adapter.validate_request(request)
            return
        version = _sdk_version()
        if version != SDK_VERSION:
            raise CapabilityError(
                f"Claude mediated profile requires {SDK_DISTRIBUTION}=={SDK_VERSION}; "
                f"found {version!r}"
            )
        sdk = importlib.import_module("claude_agent_sdk")
        required_exports = (
            "ClaudeAgentOptions",
            "ClaudeSDKClient",
            "create_sdk_mcp_server",
            "tool",
        )
        missing_exports = [name for name in required_exports if not hasattr(sdk, name)]
        if missing_exports:
            raise CapabilityError(
                "pinned Claude Agent SDK is missing required exports: "
                + ", ".join(missing_exports)
            )
        required_options = {
            "tools",
            "allowed_tools",
            "disallowed_tools",
            "mcp_servers",
            "strict_mcp_config",
            "permission_mode",
            "cwd",
            "setting_sources",
            "skills",
            "plugins",
            "system_prompt",
            "resume",
            "model",
            "effort",
            "max_turns",
            "output_format",
            "env",
        }
        try:
            option_fields = {item.name for item in dataclasses.fields(sdk.ClaudeAgentOptions)}
        except TypeError as exc:
            raise CapabilityError(
                "pinned ClaudeAgentOptions is not the audited dataclass surface"
            ) from exc
        missing_options = required_options - option_fields
        if missing_options:
            raise CapabilityError(
                "pinned Claude Agent SDK lacks required isolation options: "
                + ", ".join(sorted(missing_options))
            )
        if request.settings:
            unknown = set(request.settings) - {"max_turns"}
            if unknown:
                raise CapabilityError(
                    "Claude Agent SDK profile does not support settings: "
                    + ", ".join(sorted(unknown))
                )
            turns = request.settings.get("max_turns")
            if (
                isinstance(turns, bool)
                or not isinstance(turns, int)
                or turns < 1
                or turns > TOOL_CALL_LIMIT
            ):
                raise CapabilityError(
                    f"max_turns must be an integer from 1 through {TOOL_CALL_LIMIT}"
                )

    def cancel(self, operation_id: str) -> RecoveryOutcome:
        # The SDK query is in-process and exposes asynchronous interrupt only
        # through an active client. This synchronous profile does not claim a
        # process-tree cancellation acknowledgement.
        delegated = self._run_adapter.cancel(operation_id)
        if not isinstance(delegated, Unknown):
            return delegated
        with self._sdk_active_lock:
            active = self._sdk_active.get(operation_id)
        if active is not None:
            loop, client, stopped = active
            try:
                future = asyncio.run_coroutine_threadsafe(client.interrupt(), loop)
                future.result(timeout=2)
                stopped.wait(timeout=2)
            except BaseException as exc:
                return Unknown(
                    f"Claude SDK interrupt was requested but native quiescence "
                    f"was not confirmed: {exc}"
                )
            return Unknown(
                "Claude SDK acknowledged interrupt and its client closed, but "
                "complete native process-tree quiescence is not independently proven"
            )
        return Unknown(
            f"Claude Agent SDK attempt {operation_id!r} has no synchronous "
            "quiescence acknowledgement"
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

        # Package shape, MCP inventory, read roots, and exact grant envelopes
        # are all resolved before either a durable dispatch intent or a native
        # SDK client exists.
        sdk = importlib.import_module("claude_agent_sdk")
        tools, observations, cleanups, evidence_failures, tool_control = self._tools(
            sdk, request
        )
        try:
            configured = self._options(sdk, request, tools)
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
            "operation_id": request.operation_id,
            "attempt": request.attempt,
            "operation": request.operation.value,
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
            response = asyncio.run(
                asyncio.wait_for(
                    self._arun(
                        request,
                        sdk,
                        configured,
                        observations,
                        cleanups,
                        evidence_failures,
                        tool_control,
                    ),
                    timeout=dispatch.timeout,
                )
            )
        except _TerminalFailure as exc:
            failed = {
                **started,
                "status": "failed",
                "finished_at": _now(),
                "error": str(exc),
            }
            _atomic_json(path, failed)
            dispatch.finish("failed", error=exc)
            raise ProviderError(str(exc)) from exc
        except TimeoutError as exc:
            uncertain = {
                **started,
                "status": "uncertain",
                "finished_at": _now(),
                "error": (
                    "Claude SDK timed out after cancellation of its async client; "
                    "native process-tree quiescence was not independently proven"
                ),
            }
            _atomic_json(path, uncertain)
            dispatch.finish("timed_out", error=exc)
            raise ProviderInterruptedError(
                uncertain["error"], receipt=path
            ) from exc
        except (KeyboardInterrupt, SystemExit):
            dispatch.finish("interrupted")
            raise
        except BaseException as exc:
            if dispatched:
                uncertain = {
                    **started,
                    "status": "uncertain",
                    "finished_at": _now(),
                    "error": f"Claude SDK terminal result was not observed: {exc}",
                }
                _atomic_json(path, uncertain)
                dispatch.finish("failed", error=exc)
                raise ProviderInterruptedError(
                    uncertain["error"], receipt=path
                ) from exc
            for cleanup in cleanups:
                cleanup()
            dispatch.finish("failed", error=exc)
            raise
        try:
            completed = {
                **started,
                "status": "completed",
                "finished_at": _now(),
                "response": _response_record(response),
            }
            _atomic_json(path, completed)
        except BaseException as exc:
            dispatch.finish("failed", usage=response.usage, error=exc)
            raise ProviderError(
                f"Claude SDK result could not be durably committed: {exc}"
            ) from exc
        dispatch.finish("completed", usage=response.usage)
        return response

    def _options(self, sdk: Any, request: ProviderRequest, tools: list[Any]) -> Any:
        if tools:
            server = sdk.create_sdk_mcp_server(
                name="botpipe", version="1.0.0", tools=tools
            )
            servers: dict[str, Any] = {"botpipe": server}
            allowed = [f"mcp__botpipe__{tool.name}" for tool in tools]
        else:
            servers = {}
            allowed = []

        policy = request.policy.effective()
        options: dict[str, Any] = {
            "tools": [],
            "allowed_tools": allowed,
            "disallowed_tools": [],
            "mcp_servers": servers,
            "strict_mcp_config": True,
            "permission_mode": "dontAsk",
            "cwd": str(request.workspace),
            "setting_sources": [],
            "skills": [],
            "plugins": [],
            "system_prompt": request.instructions or "You are a Botpipe provider.",
            "resume": request.session_id,
            "model": policy.model,
            "effort": policy.effort.value if policy.effort is not None else None,
            "max_turns": request.settings.get("max_turns", TOOL_CALL_LIMIT),
            "output_format": (
                {"type": "json_schema", "schema": request.output_schema}
                if request.output_schema is not None
                else None
            ),
            # The profile's subprocess receives only caller-supplied provider
            # environment additions. Ambient settings/plugins are closed above.
            "env": dict(self.env),
        }
        options = {key: value for key, value in options.items() if value is not None}
        return sdk.ClaudeAgentOptions(**options)

    async def _arun(
        self,
        request: ProviderRequest,
        sdk: Any,
        configured: Any,
        observations: list[ToolObservation],
        cleanups: list[Any],
        evidence_failures: list[BaseException],
        tool_control: dict[str, Any],
    ) -> ProviderResponse:
        terminal: Any = None
        sink = _NATIVE_EVENT_SINK.get()
        try:
            async with sdk.ClaudeSDKClient(options=configured) as client:
                stopped = threading.Event()
                with self._sdk_active_lock:
                    self._sdk_active[request.operation_id] = (
                        asyncio.get_running_loop(),
                        client,
                        stopped,
                    )
                tool_control["client"] = client
                await client.query(request.prompt)
                async for message in client.receive_response():
                    if sink is not None:
                        event = {
                            "type": type(message).__name__,
                            "message": _plain(message),
                        }
                        sink(MappingProxyType(event))
                    if type(message).__name__ == "ResultMessage":
                        terminal = message
        finally:
            tool_control.pop("client", None)
            with self._sdk_active_lock:
                active = self._sdk_active.pop(request.operation_id, None)
            if active is not None:
                active[2].set()
            for cleanup in cleanups:
                cleanup()
        if evidence_failures:
            raise _TerminalFailure(
                f"Claude tool evidence could not be persisted: {evidence_failures[0]}"
            )
        if terminal is None:
            raise ProviderInterruptedError(
                "Claude Agent SDK ended without ResultMessage",
                receipt=receipt_path(request),
            )
        if bool(getattr(terminal, "is_error", False)) or getattr(
            terminal, "subtype", None
        ) != "success":
            error = getattr(terminal, "result", None) or getattr(
                terminal, "errors", None
            )
            raise _TerminalFailure(f"Claude SDK terminal failure: {error!s}")
        structured = getattr(terminal, "structured_output", None)
        result = (
            json.dumps(structured, ensure_ascii=False)
            if structured is not None
            else getattr(terminal, "result", None)
        )
        if not isinstance(result, str):
            raise _TerminalFailure("Claude SDK success contained no result text")
        session_id = getattr(terminal, "session_id", None) or request.session_id
        usage = getattr(terminal, "usage", {})
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        if not isinstance(usage, Mapping):
            usage = {}
        return ProviderResponse(
            result,
            session_id if isinstance(session_id, str) else None,
            dict(usage),
            {
                "provider": self.name,
                "adapter_version": self.capabilities.version,
                "tool_observations": [item.to_record() for item in observations],
            },
        )

    def _tools(
        self, sdk: Any, request: ProviderRequest
    ) -> tuple[
        list[Any], list[ToolObservation], list[Any], list[BaseException], dict[str, Any]
    ]:
        observations: list[ToolObservation] = []
        result: list[Any] = []
        cleanups: list[Any] = []
        evidence_failures: list[BaseException] = []
        tool_control: dict[str, Any] = {}
        evidence = ToolEvidence(
            request,
            self.capabilities.version,
            max_observations=TOOL_CALL_LIMIT,
            max_bytes=1_000_000,
        )

        def ensure_capacity() -> None:
            if len(observations) >= TOOL_CALL_LIMIT:
                raise CapabilityError(
                    f"native tool call limit of {TOOL_CALL_LIMIT} was reached"
                )

        async def record(observation: ToolObservation) -> dict[str, Any]:
            try:
                evidence.record(observation)
            except BaseException as exc:
                evidence_failures.append(exc)
                client = tool_control.get("client")
                interrupt = getattr(client, "interrupt", None)
                if callable(interrupt):
                    await interrupt()
                raise
            observations.append(observation)
            return _observation_result(observation)

        if request.operation is OperationKind.GENERATE:
            if not request.allow_commands:
                evidence.prepare()
                return (
                    result,
                    observations,
                    cleanups,
                    evidence_failures,
                    tool_control,
                )
            policy = request.policy.effective()
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
            cleanups.append(commands.close)
            try:
                evidence.prepare(commands.envelopes)
            except BaseException:
                commands.close()
                cleanups.clear()
                raise

            schema = {
                "type": "object",
                "properties": {
                    "grant_id": {
                        "type": "string",
                        "enum": list(commands.envelopes),
                    }
                },
                "required": ["grant_id"],
                "additionalProperties": False,
            }

            @sdk.tool(
                "exec_grant",
                "Execute one explicitly authorized read-only command envelope.",
                schema,
            )
            async def exec_grant(args: dict[str, Any]) -> dict[str, Any]:
                ensure_capacity()
                observation = commands.execute(args.get("grant_id"))
                return await record(observation)

            result.append(exec_grant)
            return result, observations, cleanups, evidence_failures, tool_control

        policy = request.policy.effective()
        roots = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.allow_read or ())
        )
        excluded = tuple(
            path if path.is_absolute() else request.workspace / path
            for path in map(Path, policy.deny_read or ())
        )
        reads = ReadOnlyTools(
            roots,
            exclusions=excluded,
            max_output_bytes=TOOL_OUTPUT_BYTES,
            read_fence=request.read_fence,
        )
        cleanups.append(reads.close)

        def register(name: str, description: str, schema: dict[str, Any], function):
            result.append(sdk.tool(name, description, schema)(function))

        async def read(args: dict[str, Any]) -> dict[str, Any]:
            ensure_capacity()
            observation = reads.read(args.get("path"))
            return await record(observation)

        async def list_dir(args: dict[str, Any]) -> dict[str, Any]:
            ensure_capacity()
            observation = reads.list(args.get("path", "."))
            return await record(observation)

        async def search(args: dict[str, Any]) -> dict[str, Any]:
            ensure_capacity()
            observation = reads.search(args.get("query"), args.get("path", "."))
            return await record(observation)

        path_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        }
        register("read", "Read an authorized non-private file.", path_schema, read)
        register(
            "list",
            "List an authorized directory.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "additionalProperties": False,
            },
            list_dir,
        )
        register(
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
            search,
        )
        try:
            evidence.prepare(reads.command_envelopes)
        except BaseException:
            for cleanup in cleanups:
                cleanup()
            cleanups.clear()
            raise
        async def count_lines(args: dict[str, Any]) -> dict[str, Any]:
            ensure_capacity()
            observation = reads.count_lines(args.get("path"))
            return await record(observation)

        register(
            "count_lines",
            "Count lines in one authorized file using a fixed native command.",
            path_schema,
            count_lines,
        )
        return result, observations, cleanups, evidence_failures, tool_control


__all__ = ["ClaudeSDKProvider", "SDK_DISTRIBUTION", "SDK_VERSION"]
