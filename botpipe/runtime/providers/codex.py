"""Runtime-backed Codex CLI transport."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import FailureContext, ProviderExecutionError
from ...core.provider_policy import ProviderPolicyEmission, ProviderPolicyValidationConfig
from ...core.providers.models import TokenUsage
from ...core.providers.protocols import ProviderTransport
from ...core.providers.rendered import RenderedLLMProvider
from ...core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from ..config import ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_policy_step_key,
    build_session_binding,
    communicate_text_subprocess,
    emit_turn_policy,
    ensure_session_provider_match,
    extract_token_usage,
    format_subprocess_streams,
    merge_subprocess_env,
    provider_metadata_with_policy,
    resumable_session_id,
    run_text_subprocess,
    structured_output_metadata,
    terminate_text_subprocess,
)
from .codex_policy import CodexPolicyEmitter


_CODEX_STDOUT_CHUNK_SIZE = 64 * 1024


class _CodexCommunicationError(Exception):
    """Raised when Codex CLI subprocess communication fails."""


@dataclass(frozen=True, slots=True)
class CodexCLICommand:
    """Resolved Codex start/resume command prefixes."""

    start_command: tuple[str, ...]
    resume_command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CodexExecSurface:
    start_help: str
    resume_help: str

    @property
    def start_supports_model(self) -> bool:
        return "--model" in self.start_help or "-m, --model" in self.start_help

    @property
    def resume_supports_model(self) -> bool:
        return "--model" in self.resume_help or "-m, --model" in self.resume_help

    @property
    def start_supports_json(self) -> bool:
        return "--json" in self.start_help

    @property
    def resume_supports_json(self) -> bool:
        return "--json" in self.resume_help

    @property
    def start_supports_model_effort(self) -> bool:
        return "--model-effort" in self.start_help

    @property
    def resume_supports_model_effort(self) -> bool:
        return "--model-effort" in self.resume_help

    @property
    def start_supports_output_schema(self) -> bool:
        return "--output-schema" in self.start_help

    @property
    def resume_supports_output_schema(self) -> bool:
        return "--output-schema" in self.resume_help

    @property
    def start_supports_skip_git_repo_check(self) -> bool:
        return "--skip-git-repo-check" in self.start_help

    @property
    def resume_supports_skip_git_repo_check(self) -> bool:
        return "--skip-git-repo-check" in self.resume_help


def verify_codex_exec_capabilities() -> None:
    """Validate the installed Codex CLI surface."""

    _validate_codex_surface(_probe_codex_exec_surface(), require_model_effort=False)


def resolve_codex_cli_commands(config: ResolvedRuntimeConfig) -> CodexCLICommand:
    """Resolve the cached Codex CLI command prefixes for the given config."""

    surface = _probe_codex_exec_surface()
    _validate_codex_surface(surface, require_model_effort=config.provider.codex.model_effort is not None)

    start_command = ["codex", "exec", "--json"]
    resume_command = ["codex", "exec", "resume", "--json"]
    if not config.runtime.git_tracking.enabled and surface.start_supports_skip_git_repo_check:
        start_command.append("--skip-git-repo-check")
    if not config.runtime.git_tracking.enabled and surface.resume_supports_skip_git_repo_check:
        resume_command.append("--skip-git-repo-check")

    return CodexCLICommand(
        start_command=tuple(arg for arg in start_command if arg),
        resume_command=tuple(arg for arg in resume_command if arg),
    )


def parse_codex_exec_json(raw_stdout: str) -> tuple[str, str | None, dict[str, Any], TokenUsage | None]:
    """Parse Codex JSONL stdout into assistant text and canonical session data."""

    assistant_messages: list[str] = []
    parsed_line_count = 0
    malformed_line_count = 0
    session_id: str | None = None
    usage = None

    for raw_line in raw_stdout.splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            malformed_line_count += 1
            continue

        if not isinstance(payload, dict):
            continue

        parsed_line_count += 1
        event_type = payload.get("type")
        if event_type == "thread.started":
            thread_id = payload.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                session_id = thread_id
        elif event_type == "item.completed":
            item = payload.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                assistant_messages.append(item["text"])
        resolved_usage = extract_token_usage(payload, source="codex")
        if resolved_usage is not None:
            usage = resolved_usage

    if parsed_line_count == 0:
        raise _adapter_output_error("provider 'codex' returned unusable JSONL output.")
    if not assistant_messages:
        raise _adapter_output_error("provider 'codex' did not return assistant text in JSONL output.")

    provider_metadata = {
        "assistant_message_count": len(assistant_messages),
        "jsonl_event_count": parsed_line_count,
        "malformed_jsonl_lines": malformed_line_count,
    }
    return "\n\n".join(assistant_messages), session_id, provider_metadata, usage


def _adapter_output_error(message: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="malformed_provider_output",
            step_name="",
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": "adapter_output"},
        ),
        retry_kind="malformed_provider_output",
    )


def _transport_error(message: str, *, step_name: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="provider_transport_failure",
            step_name=step_name,
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": "transport"},
        ),
        retry_kind="provider_transport_failure",
    )


def _session_output_error(message: str, *, step_name: str) -> ProviderExecutionError:
    return ProviderExecutionError(
        message,
        failure_context=FailureContext(
            kind="provider_transport_failure",
            step_name=step_name,
            provider_attributable=True,
            details={"error": message, "provider_failure_stage": "adapter_output"},
        ),
        retry_kind="provider_transport_failure",
    )


class CodexTransport(ProviderTransport):
    """Transport-only Codex CLI executor."""

    def __init__(
        self,
        *,
        commands: CodexCLICommand,
        model: str | None,
        model_effort: str | None,
        validation: ProviderPolicyValidationConfig | None = None,
    ) -> None:
        self._commands = commands
        self._model = model
        self._model_effort = model_effort
        self._emitter = CodexPolicyEmitter()
        self._validation = validation or ProviderPolicyValidationConfig()

    async def run_turn(self, turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("codex", turn.session)
        prompt_fingerprint = _prompt_fingerprint(turn.prompt_text)
        _emit_provider_turn_started(turn, provider_target="codex", prompt_fingerprint=prompt_fingerprint)
        interrupted_attempt = _find_interrupted_codex_attempt(turn, prompt_fingerprint=prompt_fingerprint)
        emission, base_command, model, model_effort, structured_output, cleanup_schema_path = _prepare_turn_command(
            turn,
            commands=self._commands,
            emitter=self._emitter,
            validation=self._validation,
            fallback_model=self._model,
            fallback_model_effort=self._model_effort,
            force_resume_session_id=_attempt_session_id(interrupted_attempt),
        )
        resume_session_id = resumable_session_id("codex", turn.session)
        try:
            native_resume_session_id = _attempt_session_id(interrupted_attempt)
            if native_resume_session_id is not None:
                command = [*base_command, native_resume_session_id]
                _emit_provider_attempt_recovery(
                    turn,
                    "provider_attempt_resume_started",
                    provider_target="codex",
                    session_id=native_resume_session_id,
                    prompt_fingerprint=prompt_fingerprint,
                )
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=merge_subprocess_env(None if emission is None else emission.env),
                    **_turn_cwd_kwargs(turn),
                )
                stdout, stderr = await _communicate_codex_process(process, turn=turn, input_text=None)
                if process.returncode == 0:
                    try:
                        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
                    except ProviderExecutionError as exc:
                        stderr = stderr or str(exc)
                    else:
                        provider_metadata = _with_interrupted_resume_metadata(
                            provider_metadata,
                            session_id=native_resume_session_id,
                            prompt_fingerprint=prompt_fingerprint,
                        )
                        if emission is not None:
                            provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
                        return _build_codex_result(
                            turn=turn,
                            resume_session_id=native_resume_session_id,
                            resolved_session_id=resolved_session_id,
                            provider_metadata=provider_metadata,
                            usage=usage,
                            assistant_text=assistant_text,
                            model=model,
                            model_effort=model_effort,
                            structured_output=structured_output,
                        )
                    stderr = stderr or "provider-native resume produced no usable assistant output"
                _emit_provider_attempt_recovery(
                    turn,
                    "provider_attempt_resume_failed",
                    provider_target="codex",
                    session_id=native_resume_session_id,
                    prompt_fingerprint=prompt_fingerprint,
                    error=stderr.strip() or stdout.strip() or f"exit code {process.returncode}",
                )
                _cleanup_schema_file(cleanup_schema_path)
                cleanup_schema_path = None
                fallback_force_start = _is_missing_rollout_resume_error(stderr)
                emission, base_command, model, model_effort, structured_output, cleanup_schema_path = _prepare_turn_command(
                    turn,
                    commands=self._commands,
                    emitter=self._emitter,
                    validation=self._validation,
                    fallback_model=self._model,
                    fallback_model_effort=self._model_effort,
                    force_start=fallback_force_start,
                )
                _emit_provider_attempt_recovery(
                    turn,
                    "provider_attempt_retry_started",
                    provider_target="codex",
                    session_id=native_resume_session_id,
                    prompt_fingerprint=prompt_fingerprint,
                    reason="native_resume_failed",
                )
            else:
                fallback_force_start = False

            resume_session_id = None if fallback_force_start else resumable_session_id("codex", turn.session)
            if resume_session_id is None:
                command = list(base_command)
            else:
                command = [*base_command, resume_session_id, "-"]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merge_subprocess_env(None if emission is None else emission.env),
                **_turn_cwd_kwargs(turn),
            )
            stdout, stderr = await _communicate_codex_process(process, turn=turn, input_text=turn.prompt_text)
            if process.returncode != 0:
                if resume_session_id is not None and _is_missing_rollout_resume_error(stderr):
                    _cleanup_schema_file(cleanup_schema_path)
                    cleanup_schema_path = None
                    return await self._run_fresh_turn_after_stale_resume(
                        turn,
                        stale_session_id=resume_session_id,
                    )
                streams = format_subprocess_streams(stdout, stderr)
                raise _transport_error(
                    f"provider 'codex' failed while running step {turn.step_name!r} "
                    f"(exit code {process.returncode}): {streams}",
                    step_name=turn.step_name,
                )

            assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
            if emission is not None:
                provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
            return _build_codex_result(
                turn=turn,
                resume_session_id=resume_session_id,
                resolved_session_id=resolved_session_id,
                provider_metadata=provider_metadata,
                usage=usage,
                assistant_text=assistant_text,
                model=model,
                model_effort=model_effort,
                structured_output=structured_output,
            )
        finally:
            _cleanup_schema_file(cleanup_schema_path)

    async def _run_fresh_turn_after_stale_resume(
        self,
        turn: RenderedProviderTurn,
        *,
        stale_session_id: str,
    ) -> ProviderTurnResult:
        emission, base_command, model, model_effort, structured_output, cleanup_schema_path = _prepare_turn_command(
            turn,
            commands=self._commands,
            emitter=self._emitter,
            validation=self._validation,
            fallback_model=self._model,
            fallback_model_effort=self._model_effort,
            force_start=True,
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *base_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merge_subprocess_env(None if emission is None else emission.env),
                **_turn_cwd_kwargs(turn),
            )
            stdout, stderr = await _communicate_codex_process(process, turn=turn, input_text=turn.prompt_text)
            if process.returncode != 0:
                streams = format_subprocess_streams(stdout, stderr)
                raise _transport_error(
                    f"provider 'codex' failed while running step {turn.step_name!r} "
                    f"(exit code {process.returncode}) after discarding stale resume session: {streams}",
                    step_name=turn.step_name,
                )

            assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
            provider_metadata = _with_stale_resume_metadata(provider_metadata, stale_session_id=stale_session_id)
            if emission is not None:
                provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
            return _build_codex_result(
                turn=turn,
                resume_session_id=None,
                resolved_session_id=resolved_session_id,
                provider_metadata=provider_metadata,
                usage=usage,
                assistant_text=assistant_text,
                model=model,
                model_effort=model_effort,
                structured_output=structured_output,
            )
        finally:
            _cleanup_schema_file(cleanup_schema_path)


def build_codex_transport(config: ResolvedRuntimeConfig) -> CodexTransport:
    """Build the Codex runtime transport."""

    return CodexTransport(
        commands=resolve_codex_cli_commands(config),
        model=config.provider.codex.model,
        model_effort=config.provider.codex.model_effort,
        validation=config.provider_policy.validation,
    )


def build_codex_operation_executor(
    config: ResolvedRuntimeConfig,
    *,
    commands: CodexCLICommand | None = None,
) -> Callable[[RenderedProviderTurn], ProviderTurnResult]:
    """Build the explicit sync operation executor for compatibility helpers."""

    resolved_commands = commands or resolve_codex_cli_commands(config)
    model = config.provider.codex.model
    model_effort = config.provider.codex.model_effort

    def execute(turn: RenderedProviderTurn) -> ProviderTurnResult:
        ensure_session_provider_match("codex", turn.session)
        emission, base_command, turn_model, turn_model_effort, structured_output, cleanup_schema_path = _prepare_turn_command(
            turn,
            commands=resolved_commands,
            emitter=CodexPolicyEmitter(),
            validation=config.provider_policy.validation,
            fallback_model=model,
            fallback_model_effort=model_effort,
        )
        resume_session_id = resumable_session_id("codex", turn.session)
        try:
            if resume_session_id is None:
                command = list(base_command)
            else:
                command = [*base_command, resume_session_id, "-"]
            stdout, stderr, returncode = run_text_subprocess(
                command,
                input_text=turn.prompt_text,
                env=merge_subprocess_env(None if emission is None else emission.env),
                **_turn_cwd_kwargs(turn),
            )
            if returncode != 0:
                if resume_session_id is not None and _is_missing_rollout_resume_error(stderr):
                    _cleanup_schema_file(cleanup_schema_path)
                    cleanup_schema_path = None
                    return _run_fresh_operation_after_stale_resume(
                        turn,
                        commands=resolved_commands,
                        validation=config.provider_policy.validation,
                        fallback_model=model,
                        fallback_model_effort=model_effort,
                        stale_session_id=resume_session_id,
                    )
                streams = format_subprocess_streams(stdout, stderr)
                raise _transport_error(
                    f"provider 'codex' failed while running step {turn.step_name!r} "
                    f"(exit code {returncode}): {streams}",
                    step_name=turn.step_name,
                )
            assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
            if emission is not None:
                provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
            return _build_codex_result(
                turn=turn,
                resume_session_id=resume_session_id,
                resolved_session_id=resolved_session_id,
                provider_metadata=provider_metadata,
                usage=usage,
                assistant_text=assistant_text,
                model=turn_model,
                model_effort=turn_model_effort,
                structured_output=structured_output,
            )
        finally:
            _cleanup_schema_file(cleanup_schema_path)

    return execute


def _run_fresh_operation_after_stale_resume(
    turn: RenderedProviderTurn,
    *,
    commands: CodexCLICommand,
    validation: ProviderPolicyValidationConfig,
    fallback_model: str | None,
    fallback_model_effort: str | None,
    stale_session_id: str,
) -> ProviderTurnResult:
    emission, base_command, model, model_effort, structured_output, cleanup_schema_path = _prepare_turn_command(
        turn,
        commands=commands,
        emitter=CodexPolicyEmitter(),
        validation=validation,
        fallback_model=fallback_model,
        fallback_model_effort=fallback_model_effort,
        force_start=True,
    )
    try:
        stdout, stderr, returncode = run_text_subprocess(
            list(base_command),
            input_text=turn.prompt_text,
            env=merge_subprocess_env(None if emission is None else emission.env),
            **_turn_cwd_kwargs(turn),
        )
        if returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise _transport_error(
                f"provider 'codex' failed while running step {turn.step_name!r} "
                f"(exit code {returncode}) after discarding stale resume session: {streams}",
                step_name=turn.step_name,
            )
        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
        provider_metadata = _with_stale_resume_metadata(provider_metadata, stale_session_id=stale_session_id)
        if emission is not None:
            provider_metadata = provider_metadata_with_policy(provider_metadata, emission=emission)
        return _build_codex_result(
            turn=turn,
            resume_session_id=None,
            resolved_session_id=resolved_session_id,
            provider_metadata=provider_metadata,
            usage=usage,
            assistant_text=assistant_text,
            model=model,
            model_effort=model_effort,
            structured_output=structured_output,
        )
    finally:
        _cleanup_schema_file(cleanup_schema_path)


class CodexProvider(RenderedLLMProvider):
    """Compatibility semantic provider backed by CodexTransport."""

    def __init__(self, config: ResolvedRuntimeConfig, commands: CodexCLICommand | None = None) -> None:
        resolved_commands = commands or resolve_codex_cli_commands(config)
        super().__init__(
            CodexTransport(
                commands=resolved_commands,
                model=config.provider.codex.model,
                model_effort=config.provider.codex.model_effort,
                validation=config.provider_policy.validation,
            ),
            operation_executor=build_codex_operation_executor(config, commands=resolved_commands),
        )


def build_codex_provider(config: ResolvedRuntimeConfig) -> CodexProvider:
    """Build the compatibility Codex semantic provider wrapper."""

    return CodexProvider(config)


def _build_codex_result(
    *,
    turn: RenderedProviderTurn,
    resume_session_id: str | None,
    resolved_session_id: str | None,
    provider_metadata: dict[str, Any],
    usage: TokenUsage | None,
    assistant_text: str,
    model: str | None,
    model_effort: str | None,
    structured_output: dict[str, Any] | None,
) -> ProviderTurnResult:
    if resolved_session_id is None and resume_session_id is not None:
        resolved_session_id = resume_session_id
    if resolved_session_id is None and turn.session is not None:
        raise _session_output_error(
            f"provider 'codex' did not return a resumable session_id for step {turn.step_name!r}.",
            step_name=turn.step_name,
        )

    binding = (
        build_session_binding(
            turn.session,
            session_id=resolved_session_id,
            provider_name="codex",
            provider_metadata=provider_metadata,
            model=model,
            effort=model_effort,
        )
        if turn.session is not None and resolved_session_id is not None
        else None
    )
    metadata = {
        "mode": "resume" if resume_session_id is not None else "start",
        "provider_metadata": dict(provider_metadata),
    }
    if structured_output is not None:
        metadata["structured_output"] = dict(structured_output)
    return ProviderTurnResult(raw_text=assistant_text, session=binding, metadata=metadata, usage=usage)


@lru_cache(maxsize=1)
def _probe_codex_exec_surface() -> _CodexExecSurface:
    if shutil.which("codex") is None:
        raise ConfigError("provider 'codex' is unavailable in this environment: the 'codex' CLI was not found on PATH.")

    start_help = _run_help_command(["codex", "exec", "--help"], provider_name="codex")
    resume_help = _run_help_command(["codex", "exec", "resume", "--help"], provider_name="codex")
    return _CodexExecSurface(start_help=start_help, resume_help=resume_help)


def _validate_codex_surface(surface: _CodexExecSurface, *, require_model_effort: bool) -> None:
    if not surface.start_supports_json:
        raise ConfigError("provider 'codex' requires 'codex exec --json' support, but '--json' is unavailable.")
    if not surface.resume_supports_json:
        raise ConfigError(
            "provider 'codex' requires 'codex exec resume --json' support, but '--json' is unavailable."
        )
    if not surface.start_supports_model:
        raise ConfigError("provider 'codex' requires 'codex exec --model' support, but '--model' is unavailable.")
    if not surface.resume_supports_model:
        raise ConfigError(
            "provider 'codex' requires 'codex exec resume --model' support, but '--model' is unavailable."
        )
    if require_model_effort and not surface.start_supports_model_effort:
        raise ConfigError(
            "provider 'codex' cannot honor provider.codex.model_effort because 'codex exec' does not support "
            "'--model-effort'."
        )
    if require_model_effort and not surface.resume_supports_model_effort:
        raise ConfigError(
            "provider 'codex' cannot honor provider.codex.model_effort because 'codex exec resume' does not support "
            "'--model-effort'."
        )


def _run_help_command(command: list[str], *, provider_name: str) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        streams = format_subprocess_streams(completed.stdout, completed.stderr)
        raise ConfigError(
            f"provider '{provider_name}' capability verification failed while running "
            f"{' '.join(command)!r}: {streams}"
        )
    return "\n".join(part for part in (completed.stdout, completed.stderr) if part)


def _turn_cwd(turn: RenderedProviderTurn) -> str | None:
    return None if turn.workspace_root is None else str(turn.workspace_root)


def _turn_cwd_kwargs(turn: RenderedProviderTurn) -> dict[str, str]:
    cwd = _turn_cwd(turn)
    return {} if cwd is None else {"cwd": cwd}


async def _communicate_codex_process(
    process: asyncio.subprocess.Process,
    *,
    turn: RenderedProviderTurn,
    input_text: str | None,
) -> tuple[str, str]:
    if getattr(process, "stdout", None) is None:
        stdout, stderr = await communicate_text_subprocess(process, input_text=input_text)
        for line in stdout.splitlines():
            session_id = _session_id_from_jsonl_line(line)
            if session_id is not None:
                _emit_provider_session_known(turn, provider_target="codex", session_id=session_id)
        return stdout, stderr

    stdout_parts: list[bytes] = []
    stderr_parts: list[bytes] = []
    seen_session_ids: set[str] = set()

    def handle_stdout_line(line: bytes) -> None:
        stdout_parts.append(line)
        text = line.decode("utf-8", errors="replace")
        session_id = _session_id_from_jsonl_line(text)
        if session_id is not None and session_id not in seen_session_ids:
            seen_session_ids.add(session_id)
            _emit_provider_session_known(turn, provider_target="codex", session_id=session_id)

    async def write_stdin() -> None:
        if process.stdin is None:
            return
        try:
            if input_text is not None:
                process.stdin.write(input_text.encode("utf-8"))
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, ProcessLookupError):
            return
        except Exception as exc:
            raise _CodexCommunicationError(f"writing stdin failed: {type(exc).__name__}: {exc}") from exc
        finally:
            with contextlib.suppress(BrokenPipeError, ConnectionResetError, ProcessLookupError, RuntimeError):
                process.stdin.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError, ProcessLookupError, RuntimeError):
                await process.stdin.wait_closed()

    async def read_stdout() -> None:
        if process.stdout is None:
            return
        pending_line = bytearray()
        while True:
            try:
                chunk = await process.stdout.read(_CODEX_STDOUT_CHUNK_SIZE)
            except Exception as exc:
                raise _CodexCommunicationError(f"reading stdout failed: {type(exc).__name__}: {exc}") from exc
            if not chunk:
                if pending_line:
                    handle_stdout_line(bytes(pending_line))
                return
            pending_line.extend(chunk)
            while True:
                newline_index = pending_line.find(b"\n")
                if newline_index < 0:
                    break
                line = bytes(pending_line[: newline_index + 1])
                del pending_line[: newline_index + 1]
                handle_stdout_line(line)

    async def read_stderr() -> None:
        if process.stderr is None:
            return
        try:
            raw = await process.stderr.read()
        except Exception as exc:
            raise _CodexCommunicationError(f"reading stderr failed: {type(exc).__name__}: {exc}") from exc
        if raw:
            stderr_parts.append(raw)

    tasks = [
        asyncio.create_task(write_stdin()),
        asyncio.create_task(read_stdout()),
        asyncio.create_task(read_stderr()),
    ]

    try:
        await asyncio.gather(*tasks)
        try:
            await process.wait()
        except Exception as exc:
            raise _CodexCommunicationError(f"waiting for process failed: {type(exc).__name__}: {exc}") from exc
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await terminate_text_subprocess(process)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    except _CodexCommunicationError as exc:
        for task in tasks:
            task.cancel()
        await terminate_text_subprocess(process)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise _transport_error(
            f"provider 'codex' failed while communicating with the CLI for step {turn.step_name!r}: "
            f"{exc}",
            step_name=turn.step_name,
        ) from exc
    except Exception:
        for task in tasks:
            task.cancel()
        await terminate_text_subprocess(process)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return (
        b"".join(stdout_parts).decode("utf-8", errors="replace"),
        b"".join(stderr_parts).decode("utf-8", errors="replace"),
    )


def _prompt_fingerprint(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def _attempt_event_turn_kind(turn: RenderedProviderTurn) -> str:
    return "llm" if turn.turn_kind == "step" else turn.turn_kind


def _emit_provider_turn_started(
    turn: RenderedProviderTurn,
    *,
    provider_target: str,
    prompt_fingerprint: str,
) -> None:
    if turn.runtime_event_sink is None:
        return
    payload: dict[str, object] = {
        "step_name": turn.step_name,
        "turn_kind": _attempt_event_turn_kind(turn),
        "attempt": turn.attempt,
        "max_attempts": turn.max_attempts,
        "provider_target": provider_target,
        "prompt_fingerprint": prompt_fingerprint,
        "expected_response": turn.expected_response,
    }
    if turn.step_execution_id is not None:
        payload["step_execution_id"] = turn.step_execution_id
    session_id = resumable_session_id(provider_target, turn.session)
    if session_id is not None:
        payload["session_id_before"] = session_id
    turn.runtime_event_sink("provider_turn_started", payload)


def _emit_provider_session_known(
    turn: RenderedProviderTurn,
    *,
    provider_target: str,
    session_id: str,
) -> None:
    if turn.runtime_event_sink is None:
        return
    payload: dict[str, object] = {
        "step_name": turn.step_name,
        "turn_kind": _attempt_event_turn_kind(turn),
        "attempt": turn.attempt,
        "provider_target": provider_target,
        "session_id": session_id,
    }
    if turn.step_execution_id is not None:
        payload["step_execution_id"] = turn.step_execution_id
    turn.runtime_event_sink("provider_session_known", payload)


def _emit_provider_attempt_recovery(
    turn: RenderedProviderTurn,
    event_type: str,
    **payload: object,
) -> None:
    if turn.runtime_event_sink is None:
        return
    event_payload: dict[str, object] = {
        "step_name": turn.step_name,
        "turn_kind": _attempt_event_turn_kind(turn),
        "attempt": turn.attempt,
        **payload,
    }
    if turn.step_execution_id is not None:
        event_payload["step_execution_id"] = turn.step_execution_id
    turn.runtime_event_sink(event_type, event_payload)


def _session_id_from_jsonl_line(raw_line: str) -> str | None:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("type") != "thread.started":
        return None
    session_id = payload.get("thread_id")
    return session_id if isinstance(session_id, str) and session_id else None


def _find_interrupted_codex_attempt(
    turn: RenderedProviderTurn,
    *,
    prompt_fingerprint: str,
) -> dict[str, Any] | None:
    if turn.run_folder is None:
        return None
    events_file = turn.run_folder / "events.jsonl"
    if not events_file.is_file():
        return None
    records: list[dict[str, Any]] = []
    failed_native_resume_keys: set[tuple[str | None, str, int | None, str, str]] = set()
    for event in _iter_event_records(events_file):
        event_type = event.get("event_type")
        if not _event_matches_turn(event, turn):
            continue
        if event_type == "provider_attempt_started":
            records.append(
                {
                    "status": "started",
                    "seq": event.get("seq"),
                    "step_name": event.get("step_name"),
                    "step_execution_id": event.get("step_execution_id"),
                    "turn_kind": event.get("turn_kind"),
                    "attempt": event.get("attempt"),
                }
            )
            continue
        if not records:
            continue
        current = records[-1]
        if event_type == "provider_turn_started":
            current["prompt_fingerprint"] = event.get("prompt_fingerprint")
            current["session_id_before"] = event.get("session_id_before")
        elif event_type == "provider_session_known":
            current["provider_session_id"] = event.get("session_id")
            current["status"] = "session_known"
        elif event_type == "provider_attempt_resume_started":
            current["status"] = "resume_started"
        elif event_type == "provider_attempt_resume_failed":
            current["status"] = "resume_failed"
            failed_key = _native_resume_failure_key(event, current)
            if failed_key is not None:
                failed_native_resume_keys.add(failed_key)
        elif event_type in {"provider_attempt_finished", "provider_attempt_failed"}:
            current["status"] = "finished" if event_type == "provider_attempt_finished" else "failed"
    for record in reversed(records):
        if record.get("status") in {"finished", "failed", "resume_failed"}:
            continue
        session_id = record.get("provider_session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        if record.get("prompt_fingerprint") != prompt_fingerprint:
            continue
        if _attempt_record_key(record, session_id=session_id, prompt_fingerprint=prompt_fingerprint) in failed_native_resume_keys:
            continue
        return record
    return None


def _iter_event_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for raw in lines:
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _event_matches_turn(event: Mapping[str, Any], turn: RenderedProviderTurn) -> bool:
    if event.get("step_name") != turn.step_name:
        return False
    if event.get("turn_kind") != _attempt_event_turn_kind(turn):
        return False
    if event.get("attempt") != turn.attempt:
        return False
    event_step_execution_id = event.get("step_execution_id")
    if turn.step_execution_id is not None:
        return event_step_execution_id == turn.step_execution_id
    return True


def _native_resume_failure_key(
    event: Mapping[str, Any],
    current: Mapping[str, Any],
) -> tuple[str | None, str, int | None, str, str] | None:
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        session_id = current.get("provider_session_id")
    prompt_fingerprint = event.get("prompt_fingerprint")
    if not isinstance(prompt_fingerprint, str) or not prompt_fingerprint:
        prompt_fingerprint = current.get("prompt_fingerprint")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(prompt_fingerprint, str) or not prompt_fingerprint:
        return None
    return _attempt_record_key(current, session_id=session_id, prompt_fingerprint=prompt_fingerprint)


def _attempt_record_key(
    record: Mapping[str, Any],
    *,
    session_id: str,
    prompt_fingerprint: str,
) -> tuple[str | None, str, int | None, str, str]:
    step_execution_id = record.get("step_execution_id")
    turn_kind = record.get("turn_kind")
    attempt = record.get("attempt")
    return (
        step_execution_id if isinstance(step_execution_id, str) else None,
        turn_kind if isinstance(turn_kind, str) else "",
        attempt if isinstance(attempt, int) else None,
        prompt_fingerprint,
        session_id,
    )


def _attempt_session_id(attempt: Mapping[str, Any] | None) -> str | None:
    if attempt is None:
        return None
    session_id = attempt.get("provider_session_id")
    return session_id if isinstance(session_id, str) and session_id else None


def _with_interrupted_resume_metadata(
    provider_metadata: dict[str, Any],
    *,
    session_id: str,
    prompt_fingerprint: str,
) -> dict[str, Any]:
    metadata = dict(provider_metadata)
    metadata["interrupted_turn_resume"] = {
        "mode": "provider_native_no_prompt",
        "session_id": session_id,
        "prompt_fingerprint": prompt_fingerprint,
    }
    return metadata


def _prepare_turn_command(
    turn: RenderedProviderTurn,
    *,
    commands: CodexCLICommand,
    emitter: CodexPolicyEmitter,
    validation: ProviderPolicyValidationConfig,
    fallback_model: str | None,
    fallback_model_effort: str | None,
    force_start: bool = False,
    force_resume_session_id: str | None = None,
) -> tuple[
    ProviderPolicyEmission | None,
    tuple[str, ...],
    str | None,
    str | None,
    dict[str, Any] | None,
    Path | None,
]:
    emission = emit_turn_policy(emitter, turn, provider_target="codex", validation=validation)
    resume_session_id = force_resume_session_id or (None if force_start else resumable_session_id("codex", turn.session))
    command = commands.resume_command if resume_session_id is not None else commands.start_command
    model = fallback_model
    model_effort = fallback_model_effort
    if turn.policy is not None:
        model = turn.policy.model.default or model
        model_effort = turn.policy.model.effort or model_effort
    if emission is not None and emission.cli_args:
        command = (*command, *emission.cli_args)
    if turn.policy is None or turn.policy.model.default is None:
        if fallback_model:
            command = (*command, "--model", fallback_model)
    if turn.policy is None or turn.policy.model.effort is None:
        if fallback_model_effort:
            command = (*command, "--model-effort", fallback_model_effort)
    structured_output, cleanup_schema_path, schema_args = _prepare_structured_output(turn, resume_session_id=resume_session_id)
    if schema_args:
        command = (*command, *schema_args)
    return emission, command, model, model_effort, structured_output, cleanup_schema_path


def _is_missing_rollout_resume_error(stderr: str) -> bool:
    return "thread/resume" in stderr and "no rollout found for thread id" in stderr


def _with_stale_resume_metadata(
    provider_metadata: dict[str, Any],
    *,
    stale_session_id: str,
) -> dict[str, Any]:
    metadata = dict(provider_metadata)
    metadata["resume_recovery"] = {
        "reason": "missing_rollout",
        "discarded_session_id": stale_session_id,
    }
    return metadata


def _prepare_structured_output(
    turn: RenderedProviderTurn,
    *,
    resume_session_id: str | None,
) -> tuple[dict[str, Any] | None, Path | None, tuple[str, ...]]:
    if turn.response_schema is None:
        return None, None, ()
    if turn.native_response_schema is None:
        fallback_reason = turn.response_schema_native_skip_reason or "provider_response_schema_native_schema_unavailable"
        return (
            structured_output_metadata(
                provider_name="codex",
                delivery_mode="prompt_only",
                reason=fallback_reason,
            ),
            None,
            (),
        )
    surface = _probe_codex_exec_surface()
    if resume_session_id is None and surface.start_supports_output_schema:
        schema_path, cleanup_schema_path = _write_response_schema_file(turn, schema=turn.native_response_schema)
        return (
            structured_output_metadata(
                provider_name="codex",
                delivery_mode="native_full",
                schema_path=str(schema_path),
            ),
            cleanup_schema_path,
            ("--output-schema", str(schema_path)),
        )
    reason = (
        "resume_command_does_not_support_output_schema"
        if resume_session_id is not None and not surface.resume_supports_output_schema
        else "backend_does_not_support_output_schema"
    )
    return (
        structured_output_metadata(
            provider_name="codex",
            delivery_mode="prompt_only",
            reason=reason,
        ),
        None,
        (),
    )


def _write_response_schema_file(turn: RenderedProviderTurn, *, schema: Mapping[str, Any]) -> tuple[Path, Path | None]:
    schema_payload = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if turn.run_folder is not None:
        step_key = build_policy_step_key(turn.step_name, step_execution_id=turn.step_execution_id)
        schema_dir = turn.run_folder / "provider_response_schemas" / "codex"
        schema_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_dir / f"{step_key}__{turn.turn_kind}.json"
        schema_path.write_text(schema_payload, encoding="utf-8")
        return schema_path, None
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="botpipe-codex-schema-",
        delete=False,
    )
    try:
        handle.write(schema_payload)
    finally:
        handle.close()
    schema_path = Path(handle.name)
    return schema_path, schema_path


def _cleanup_schema_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
