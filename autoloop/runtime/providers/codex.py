"""Runtime-backed Codex CLI transport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...core.errors import ProviderExecutionError
from ...core.provider_policy import ProviderPolicyEmission, ProviderPolicyValidationConfig, policy_fingerprint
from ...core.providers.models import TokenUsage
from ...core.providers.protocols import ProviderTransport
from ...core.providers.rendered import RenderedLLMProvider
from ...core.providers.turns import ProviderTurnResult, RenderedProviderTurn
from ...core.stores.protocols import SessionBinding
from ..config import ConfigError, ResolvedRuntimeConfig
from ._common import (
    build_policy_step_key,
    build_session_binding,
    communicate_text_subprocess,
    ensure_session_provider_match,
    extract_token_usage,
    format_subprocess_streams,
    merge_subprocess_env,
    run_text_subprocess,
)
from .codex_policy import CodexPolicyEmitter


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


def verify_codex_exec_capabilities() -> None:
    """Validate the installed Codex CLI surface."""

    _validate_codex_surface(_probe_codex_exec_surface(), require_model_effort=False)


def resolve_codex_cli_commands(config: ResolvedRuntimeConfig) -> CodexCLICommand:
    """Resolve the cached Codex CLI command prefixes for the given config."""

    surface = _probe_codex_exec_surface()
    _validate_codex_surface(surface, require_model_effort=config.provider.codex.model_effort is not None)

    start_command = ["codex", "exec", "--json"]
    resume_command = ["codex", "exec", "resume", "--json"]

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
        raise ProviderExecutionError("provider 'codex' returned unusable JSONL output.")
    if not assistant_messages:
        raise ProviderExecutionError("provider 'codex' did not return assistant text in JSONL output.")

    provider_metadata = {
        "assistant_message_count": len(assistant_messages),
        "jsonl_event_count": parsed_line_count,
        "malformed_jsonl_lines": malformed_line_count,
    }
    return "\n\n".join(assistant_messages), session_id, provider_metadata, usage


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
        resume_session_id = _resumable_session_id("codex", turn.session)
        emission, base_command, model, model_effort = _prepare_turn_command(
            turn,
            commands=self._commands,
            emitter=self._emitter,
            validation=self._validation,
            fallback_model=self._model,
            fallback_model_effort=self._model_effort,
        )
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
        )
        stdout, stderr = await communicate_text_subprocess(process, input_text=turn.prompt_text)
        if process.returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise ProviderExecutionError(
                f"provider 'codex' failed while running step {turn.step_name!r} "
                f"(exit code {process.returncode}): {streams}"
            )

        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
        if emission is not None:
            provider_metadata = _with_policy_metadata(provider_metadata, emission=emission)
        return _build_codex_result(
            turn=turn,
            resume_session_id=resume_session_id,
            resolved_session_id=resolved_session_id,
            provider_metadata=provider_metadata,
            usage=usage,
            assistant_text=assistant_text,
            model=model,
            model_effort=model_effort,
        )


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
        resume_session_id = _resumable_session_id("codex", turn.session)
        emission, base_command, turn_model, turn_model_effort = _prepare_turn_command(
            turn,
            commands=resolved_commands,
            emitter=CodexPolicyEmitter(),
            validation=config.provider_policy.validation,
            fallback_model=model,
            fallback_model_effort=model_effort,
        )
        if resume_session_id is None:
            command = list(base_command)
        else:
            command = [*base_command, resume_session_id, "-"]
        stdout, stderr, returncode = run_text_subprocess(
            command,
            input_text=turn.prompt_text,
            env=merge_subprocess_env(None if emission is None else emission.env),
        )
        if returncode != 0:
            streams = format_subprocess_streams(stdout, stderr)
            raise ProviderExecutionError(
                f"provider 'codex' failed while running step {turn.step_name!r} "
                f"(exit code {returncode}): {streams}"
            )
        assistant_text, resolved_session_id, provider_metadata, usage = parse_codex_exec_json(stdout)
        if emission is not None:
            provider_metadata = _with_policy_metadata(provider_metadata, emission=emission)
        return _build_codex_result(
            turn=turn,
            resume_session_id=resume_session_id,
            resolved_session_id=resolved_session_id,
            provider_metadata=provider_metadata,
            usage=usage,
            assistant_text=assistant_text,
            model=turn_model,
            model_effort=turn_model_effort,
        )

    return execute


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
) -> ProviderTurnResult:
    if resolved_session_id is None and resume_session_id is not None:
        resolved_session_id = resume_session_id
    if resolved_session_id is None and turn.session is not None:
        raise ProviderExecutionError(
            f"provider 'codex' did not return a resumable session_id for step {turn.step_name!r}."
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


def _resumable_session_id(provider_name: str, session: SessionBinding | None) -> str | None:
    if session is None:
        return None
    seen_provider = session.metadata.get("provider")
    if seen_provider == provider_name and session.session_id:
        return session.session_id
    return None


def _prepare_turn_command(
    turn: RenderedProviderTurn,
    *,
    commands: CodexCLICommand,
    emitter: CodexPolicyEmitter,
    validation: ProviderPolicyValidationConfig,
    fallback_model: str | None,
    fallback_model_effort: str | None,
) -> tuple[ProviderPolicyEmission | None, tuple[str, ...], str | None, str | None]:
    emission = _emit_turn_policy(emitter, turn, validation=validation)
    resume_session_id = _resumable_session_id("codex", turn.session)
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
    return emission, command, model, model_effort


def _emit_turn_policy(
    emitter: CodexPolicyEmitter,
    turn: RenderedProviderTurn,
    *,
    validation: ProviderPolicyValidationConfig,
) -> ProviderPolicyEmission | None:
    if turn.policy is None or turn.run_folder is None:
        return None
    step_key = build_policy_step_key(turn.step_name, step_execution_id=turn.step_execution_id)
    effective_policy_path = turn.run_folder / "provider_policy" / step_key / "codex" / "effective_policy.json"
    capability_report_path = turn.run_folder / "provider_policy" / step_key / "codex" / "capability_report.json"
    try:
        emission = emitter.emit(
            turn.policy,
            run_dir=turn.run_folder,
            step_key=step_key,
            validation=validation,
            step_name=turn.step_name,
        )
    except ProviderExecutionError:
        _emit_policy_event(
            turn,
            "provider_policy_emitted",
            provider_target="codex",
            policy_fingerprint=None if turn.policy is None else policy_fingerprint(turn.policy),
            decision="fail",
            effective_policy_path=str(effective_policy_path),
            capability_report_path=str(capability_report_path),
        )
        _emit_policy_event(
            turn,
            "provider_policy_capability_report",
            provider_target="codex",
            policy_fingerprint=None if turn.policy is None else policy_fingerprint(turn.policy),
            decision="fail",
            capability_report_path=str(capability_report_path),
        )
        raise
    _emit_policy_event(
        turn,
        "provider_policy_emitted",
        provider_target="codex",
        policy_fingerprint=emission.capability_report.policy_fingerprint,
        decision=emission.capability_report.decision,
        effective_policy_path=str(emission.config_files["effective_policy"]),
        capability_report_path=str(emission.config_files["capability_report"]),
    )
    _emit_policy_event(
        turn,
        "provider_policy_capability_report",
        provider_target="codex",
        policy_fingerprint=emission.capability_report.policy_fingerprint,
        decision=emission.capability_report.decision,
        capability_report_path=str(emission.config_files["capability_report"]),
    )
    return emission


def _with_policy_metadata(
    provider_metadata: dict[str, Any],
    *,
    emission: ProviderPolicyEmission,
) -> dict[str, Any]:
    metadata = dict(provider_metadata)
    metadata["policy"] = {
        "effective_policy_file": str(emission.config_files["effective_policy"]),
        "capability_report_file": str(emission.config_files["capability_report"]),
        "policy_fingerprint": emission.capability_report.policy_fingerprint,
    }
    return metadata


def _emit_policy_event(turn: RenderedProviderTurn, event_type: str, **fields: object) -> None:
    if turn.runtime_event_sink is None:
        return
    payload: dict[str, object] = {
        "step_name": turn.step_name,
        "turn_kind": turn.turn_kind,
    }
    if turn.step_execution_id is not None:
        payload["step_execution_id"] = turn.step_execution_id
    payload.update(fields)
    turn.runtime_event_sink(event_type, payload)
